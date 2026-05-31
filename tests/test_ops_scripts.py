import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import add_sources
import migrate
import run_pipeline
import verify_production
import verify_release
from src import db
from src.collector.dispatcher import SourceFetchResult
from verify_feeds import verify


class FakeConn:
    def __init__(self, calls):
        self.calls = calls

    async def execute(self, statement, params=None):
        """Capture executed SQL text for migration assertions."""
        self.calls.append((str(statement), params))

        class FakeResult:
            def __iter__(self_inner):
                return iter(())

        return FakeResult()


class FakeBegin:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        """Return a fake connection inside the async context manager."""
        return FakeConn(self.calls)

    async def __aexit__(self, exc_type, exc, tb):
        """Propagate exceptions out of the fake async context manager."""
        return False


class FakeEngine:
    def __init__(self):
        self.calls = []

    def begin(self):
        """Return the fake begin context used by migration tests."""
        return FakeBegin(self.calls)


def test_split_sql_ignores_comments_and_blank_lines():
    sql = """
-- initial comment

CREATE TABLE one (id INT);

-- second comment
CREATE TABLE two (id INT);
"""

    assert migrate.split_sql(sql) == ["CREATE TABLE one (id INT)", "CREATE TABLE two (id INT)"]


def test_list_migration_files_requires_numbered_sql_names(tmp_path):
    (tmp_path / "001_init.sql").write_text("CREATE TABLE one (id INT);\n", encoding="utf-8")
    (tmp_path / "002_add_runs.sql").write_text("ALTER TABLE one ADD COLUMN name TEXT;\n", encoding="utf-8")

    files = migrate.list_migration_files(tmp_path)

    assert [path.name for path in files] == ["001_init.sql", "002_add_runs.sql"]
    assert migrate.latest_migration_path(tmp_path).name == "002_add_runs.sql"


def test_list_migration_files_rejects_invalid_names(tmp_path):
    (tmp_path / "init.sql").write_text("CREATE TABLE one (id INT);\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid migration filename"):
        migrate.list_migration_files(tmp_path)


def test_repo_migrations_are_numbered_and_latest_runtime_patch_exists():
    files = migrate.list_migration_files(Path("migrations"))

    assert [path.name for path in files] == ["001_init.sql", "002_deep_analysis_runtime_columns.sql"]
    assert "claimed_at" in files[-1].read_text(encoding="utf-8")


def test_build_ssl_context_respects_verify_tls_setting(monkeypatch):
    monkeypatch.setattr(db.settings, "database_verify_tls", False)
    insecure = db.build_ssl_context()

    monkeypatch.setattr(db.settings, "database_verify_tls", True)
    secure = db.build_ssl_context()

    assert insecure.verify_mode != secure.verify_mode
    assert insecure.check_hostname is False
    assert secure.check_hostname is True


@pytest.mark.asyncio
async def test_apply_sql_executes_statements_in_migration_file(tmp_path, monkeypatch):
    path = tmp_path / "migration.sql"
    path.write_text("CREATE TABLE one (id INT);\n\nCREATE TABLE two (id INT);\n", encoding="utf-8")
    fake_engine = FakeEngine()
    monkeypatch.setattr(migrate, "engine", fake_engine)

    await migrate.apply_sql(path)

    assert fake_engine.calls == [("CREATE TABLE one (id INT)", None), ("CREATE TABLE two (id INT)", None)]


@pytest.mark.asyncio
async def test_apply_pending_records_versions_after_running_sql(tmp_path, monkeypatch):
    (tmp_path / "001_init.sql").write_text("CREATE TABLE one (id INT);\n", encoding="utf-8")
    (tmp_path / "002_more.sql").write_text("ALTER TABLE one ADD COLUMN name TEXT;\n", encoding="utf-8")
    fake_engine = FakeEngine()

    async def fake_applied_versions(_engine):
        return {"001_init.sql"}

    monkeypatch.setattr(migrate, "applied_versions", fake_applied_versions)

    applied = await migrate.apply_pending(fake_engine, tmp_path)

    assert applied == ["002_more.sql"]
    assert fake_engine.calls[-1][1] == {"version": "002_more.sql"}


@pytest.mark.asyncio
async def test_verify_feeds_fails_when_catalog_is_missing(tmp_path):
    missing = tmp_path / "missing.json"

    status = await verify(str(missing), min_ok=1, include_internal=False)

    assert status == 2


@pytest.mark.asyncio
async def test_verify_feeds_times_out_individual_sources(tmp_path):
    source_file = tmp_path / "sources.json"
    source_file.write_text(
        """
[
  {
    "id": "security_nvd_cve",
    "name": "NVD CVE Feed",
    "domain": "security",
    "type": "api",
    "url": "https://services.nvd.nist.gov/rest/json/cves/2.0",
    "authority": "official",
    "fetch_strategy": "l1_api",
    "config_json": {"collector": "nvd"}
  }
]
""",
        encoding="utf-8",
    )

    async def slow_fetcher(source):
        await asyncio.sleep(1)
        raise AssertionError(f"unexpected completion for {source.id}")

    status = await verify(
        str(source_file),
        min_ok=1,
        include_internal=False,
        timeout_s=0.01,
        fetcher=slow_fetcher,
    )

    assert status == 1


def test_add_sources_only_builds_deferred_inactive_proposals():
    entries = add_sources.build_entries()

    assert entries
    assert {entry.status for entry in entries} == {"deferred"}
    assert {entry.is_active for entry in entries} == {False}
    assert "approved" not in add_sources.entries_as_json(entries)
    assert {"general", "finance"} <= {entry.domain for entry in entries}


@pytest.mark.asyncio
async def test_run_pipeline_dry_run_rolls_back_and_reports_summary(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.flushed = 0
            self.rolled_back = 0
            self.committed = 0

        async def flush(self):
            self.flushed += 1

        async def rollback(self):
            self.rolled_back += 1

        async def commit(self):
            self.committed += 1

    class FakeSessionContext:
        def __init__(self):
            self.session = FakeSession()

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    session_context = FakeSessionContext()

    async def fake_run_daily_pipeline(session, analyzer, options, *, collector, stats_updater):
        assert options.oss_config is None
        assert callable(collector)
        await stats_updater({"stage": "fetch"})
        await stats_updater({"stage": "done"})
        return SimpleNamespace(status="succeeded", stats_json={"stage": "done"})

    async def fake_run_with_lifecycle(session, **kwargs):
        run = SimpleNamespace(
            id=kwargs["run_id"],
            window_start=kwargs["window_start"],
            window_end=kwargs["window_end"],
            stats_json={},
        )
        status, stats_json = await kwargs["runner"](run)
        run.stats_json = stats_json
        return SimpleNamespace(status=status, skipped_reason=None, run=run)

    async def fake_load_approved_sources(session):
        return [SimpleNamespace(id="security_nvd_cve", domain="security")]

    async def fake_compute_run_window(session, now):
        return (
            datetime(2026, 5, 30, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

    fake_deps = SimpleNamespace(
        Analyzer=SimpleNamespace(nvidia_from_settings=lambda: object()),
        PipelineOptions=lambda **kwargs: SimpleNamespace(**kwargs),
        async_session=lambda: session_context,
        compute_run_window=fake_compute_run_window,
        load_approved_sources=fake_load_approved_sources,
        run_daily_pipeline=fake_run_daily_pipeline,
        run_with_lifecycle=fake_run_with_lifecycle,
    )
    monkeypatch.setattr(run_pipeline, "_pipeline_deps", lambda: fake_deps)

    summary = await run_pipeline.dry_run_pipeline()

    assert summary["status"] == "succeeded"
    assert summary["source_count"] == 1
    assert summary["stats_updates"] == 2
    assert summary["stats"] == {"stage": "done"}
    assert session_context.session.rolled_back == 1
    assert session_context.session.committed == 0


@pytest.mark.asyncio
async def test_run_pipeline_limited_collector_caps_items_per_domain(monkeypatch):
    async def fake_collect_sources(sources, since=None):
        return [
            SourceFetchResult(source_id="ai_hackernews", status="succeeded", items=[1, 2, 3]),
            SourceFetchResult(source_id="ai_openai_blog", status="succeeded", items=[4, 5]),
            SourceFetchResult(source_id="security_nvd_cve", status="succeeded", items=[6, 7, 8]),
            SourceFetchResult(source_id="security_exploitdb", status="succeeded", items=[9]),
        ]

    monkeypatch.setattr("src.collector.dispatcher.collect_sources", fake_collect_sources)

    results = await run_pipeline._limited_collector(
        2,
        {
            "ai_hackernews": "ai",
            "ai_openai_blog": "ai",
            "security_nvd_cve": "security",
            "security_exploitdb": "security",
        },
    )([], since=None)

    assert [result.items for result in results] == [[1, 2], [], [6, 7], []]


def test_run_pipeline_unlimited_collector_uses_real_collector():
    assert run_pipeline._limited_collector(0).__name__ == "collect_sources"


def test_docker_release_path_matches_runtime_requirements():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
    makefile = (root / "Makefile").read_text(encoding="utf-8")

    assert dockerfile.index("COPY src/ src/") < dockerfile.index("RUN uv pip install --system --no-cache .")
    assert "--loop asyncio" in dockerfile
    assert "--loop asyncio" in compose
    assert ".env" in dockerignore
    assert ".venv" in dockerignore
    assert "verify_release.py" in makefile


def test_verify_release_starts_temp_api_and_always_stops_container(monkeypatch, capsys):
    calls = []

    def fake_run(args, capture=False):
        calls.append(args)
        return SimpleNamespace(stdout="container-id\n")

    def fake_stop_container(name):
        calls.append(["docker", "stop", name])

    responses = {
        "http://127.0.0.1:18123/health": {"status": "ok"},
        "http://127.0.0.1:18123/api/v1/sources/security_nvd_cve": {"data": {"id": "security_nvd_cve"}},
    }

    monkeypatch.setattr(verify_release, "_run", fake_run)
    monkeypatch.setattr(verify_release, "_stop_container", fake_stop_container)
    monkeypatch.setattr(verify_release, "_wait_json", lambda url, timeout_s: responses[url])
    monkeypatch.setattr(
        verify_release,
        "parse_args",
        lambda: SimpleNamespace(
            port=18123,
            name="release-test",
            image="intelligence-system-api",
            timeout_s=1.0,
            skip_build=True,
        ),
    )

    assert verify_release.main() == 0

    assert calls[0][:5] == ["docker", "run", "-d", "--name", "release-test"]
    assert calls[0][-3:] == ["sh", "-c", "uvicorn src.main:app --host 127.0.0.1 --port 18123 --loop asyncio"]
    assert calls[-1] == ["docker", "stop", "release-test"]
    assert '"status": "ok"' in capsys.readouterr().out


def test_verify_production_accepts_latest_partial_run_with_persisted_artifacts(tmp_path):
    run = SimpleNamespace(
        id="run_20260531_080000",
        status="partial",
        started_at=datetime(2026, 5, 31, 8, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 31, 8, 35, tzinfo=timezone.utc),
        stats_json={
            "digest": {
                "security": {"status": "succeeded", "digest_id": "2026-05-31:security"},
                "ai": {"status": "succeeded", "digest_id": "2026-05-31:ai"},
            }
        },
    )
    security_digest = SimpleNamespace(
        id="2026-05-31:security",
        domain="security",
        date=SimpleNamespace(isoformat=lambda: "2026-05-31"),
        content_markdown="# security",
        oss_url="https://example.test/security.md",
    )
    ai_digest = SimpleNamespace(
        id="2026-05-31:ai",
        domain="ai",
        date=SimpleNamespace(isoformat=lambda: "2026-05-31"),
        content_markdown="# ai",
        oss_url="https://example.test/ai.md",
    )
    (tmp_path / "intelligence-security-2026-05-31.md").write_text("# security", encoding="utf-8")
    (tmp_path / "intelligence-ai-2026-05-31.md").write_text("# ai", encoding="utf-8")

    ok, summary = verify_production.evaluate_evidence(
        {
            "run": run,
            "item_count": 115,
            "analyzed_count": 45,
            "digests": [security_digest, ai_digest],
            "applied_migrations": ["001_init.sql", "002_deep_analysis_runtime_columns.sql"],
        },
        domains=["security", "ai"],
        posts_dir=tmp_path,
        min_items=1,
        min_analyzed=1,
        min_digests=2,
        accepted_statuses={"succeeded", "partial"},
        require_hexo_files=True,
    )

    assert ok is True
    assert summary["status"] == "ok"
    assert summary["migrations"]["ok"] is True
    assert summary["migrations"]["pending"] == []
    assert summary["run"]["id"] == "run_20260531_080000"
    assert {digest["domain"] for digest in summary["digests"]} == {"security", "ai"}


def test_verify_production_rejects_missing_hexo_or_digest_mismatch(tmp_path):
    run = SimpleNamespace(
        id="run_bad",
        status="succeeded",
        started_at=None,
        finished_at=None,
        stats_json={"digest": {"security": {"status": "succeeded", "digest_id": "expected"}}},
    )
    digest = SimpleNamespace(
        id="actual",
        domain="security",
        date=SimpleNamespace(isoformat=lambda: "2026-05-31"),
        content_markdown="# security",
        oss_url=None,
    )

    ok, summary = verify_production.evaluate_evidence(
        {
            "run": run,
            "item_count": 1,
            "analyzed_count": 1,
            "digests": [digest],
            "applied_migrations": ["001_init.sql", "002_deep_analysis_runtime_columns.sql"],
        },
        domains=["security"],
        posts_dir=tmp_path,
        min_items=1,
        min_analyzed=1,
        min_digests=1,
        accepted_statuses={"succeeded", "partial"},
        require_hexo_files=True,
    )

    assert ok is False
    assert "digest_id_mismatch:security" in summary["errors"]
    assert "missing_hexo_file:intelligence-security-2026-05-31.md" in summary["errors"]


def test_verify_production_rejects_bad_migration_policy(monkeypatch, tmp_path):
    run = SimpleNamespace(
        id="run_bad_migration",
        status="succeeded",
        started_at=None,
        finished_at=None,
        stats_json={"digest": {}},
    )
    monkeypatch.setattr(verify_production, "_migration_summary", lambda _applied: {"ok": False, "error": "bad naming"})

    ok, summary = verify_production.evaluate_evidence(
        {"run": run, "item_count": 1, "analyzed_count": 1, "digests": [], "applied_migrations": []},
        domains=[],
        posts_dir=tmp_path,
        min_items=1,
        min_analyzed=1,
        min_digests=0,
        accepted_statuses={"succeeded", "partial"},
        require_hexo_files=False,
    )

    assert ok is False
    assert summary["migrations"] == {"ok": False, "error": "bad naming"}
    assert "migration_policy_failed" in summary["errors"]


def test_verify_production_rejects_pending_migrations(tmp_path):
    run = SimpleNamespace(
        id="run_pending_migration",
        status="succeeded",
        started_at=None,
        finished_at=None,
        stats_json={"digest": {}},
    )

    ok, summary = verify_production.evaluate_evidence(
        {"run": run, "item_count": 1, "analyzed_count": 1, "digests": [], "applied_migrations": ["001_init.sql"]},
        domains=[],
        posts_dir=tmp_path,
        min_items=1,
        min_analyzed=1,
        min_digests=0,
        accepted_statuses={"succeeded", "partial"},
        require_hexo_files=False,
    )

    assert ok is False
    assert summary["migrations"]["pending"] == ["002_deep_analysis_runtime_columns.sql"]
    assert "migration_policy_failed" in summary["errors"]
