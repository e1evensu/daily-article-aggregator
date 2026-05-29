from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.ai.analyzer import DigestOverviewOutcome, Stage1Outcome, Stage2Outcome
from src.ai.contracts import DigestOverviewAnalysis, Stage1Analysis, Stage2Analysis
from src.collector.base import RawItem
from src.collector.dispatcher import SourceFetchResult
from src.models.source import Source
from src.pipeline.output import OSSConfig, OutputError
from src.pipeline.runner import PipelineOptions, run_daily_pipeline


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeExecuteResult:
    def __init__(self, scalar_values=None, scalar_one=None, rowcount=0):
        self.scalar_values = scalar_values or []
        self.scalar_one = scalar_one
        self.rowcount = rowcount

    def scalars(self):
        return FakeScalarResult(self.scalar_values)

    def scalar_one_or_none(self):
        return self.scalar_one


class FakeSession:
    def __init__(self, sources):
        self.sources = sources
        self.items_by_hash = {}
        self.added = []

    async def execute(self, statement):
        text = str(statement)
        if "FROM sources" in text:
            return FakeExecuteResult(scalar_values=self.sources)
        if "FROM items" in text and "SELECT" in text:
            where = list(statement._where_criteria)[0]
            dedup_hash = where.right.value
            return FakeExecuteResult(scalar_one=self.items_by_hash.get(dedup_hash))
        if "DELETE FROM items" in text:
            return FakeExecuteResult(rowcount=0)
        return FakeExecuteResult()

    def add(self, obj):
        self.added.append(obj)
        if hasattr(obj, "dedup_hash"):
            self.items_by_hash[obj.dedup_hash] = obj


class FakeAnalyzer:
    def __init__(self, overview="AI overview"):
        self.overview = overview
        self.overview_calls = []

    async def analyze_stage1(self, item, source):
        score = 88 if item["title"].startswith("High") else 55
        return Stage1Outcome(
            analysis=Stage1Analysis(
                category="vulnerability" if source["id"].startswith("security") else "product",
                tags=["tag"],
                summary_zh=f"{item['title']} 摘要",
                insight_score=score,
                credibility="high",
            ),
            provider="nvidia",
            model="deepseek-ai/deepseek-v4-flash",
            prompt_version="s1_v1",
            analyzed_at=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
            expires_at=None,
            error=None,
        )

    async def generate_digest_overview(self, domain, items):
        self.overview_calls.append((domain, items))
        if self.overview is None:
            return DigestOverviewOutcome(
                analysis=None,
                provider=None,
                model="deepseek-ai/deepseek-v4-flash",
                prompt_version="digest_v1",
                analyzed_at=datetime(2026, 5, 26, 9, 30, tzinfo=timezone.utc),
                error="model_parse_error",
            )
        return DigestOverviewOutcome(
            analysis=DigestOverviewAnalysis(overview_zh=self.overview),
            provider="nvidia",
            model="deepseek-ai/deepseek-v4-flash",
            prompt_version="digest_v1",
            analyzed_at=datetime(2026, 5, 26, 9, 30, tzinfo=timezone.utc),
            error=None,
        )

    async def analyze_stage2(self, item, source, also_seen_in=None):
        return Stage2Outcome(
            analysis=Stage2Analysis(
                recommendation_reason="值得处理",
                confidence="firm",
                trend_signal="growing",
                action_suggestion="跟进",
            ),
            provider="nvidia",
            model="deepseek-ai/deepseek-v4-pro",
            prompt_version="s2_v1",
            analyzed_at=datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc),
            error=None,
        )


def _source(source_id="security_nvd_cve", domain="security", status="approved"):
    source = Source(
        id=source_id,
        name=source_id,
        domain=domain,
        type="api",
        url="https://example.com/feed",
        auth_mode="none",
        fetch_strategy="l1_api",
        authority="official",
        status=status,
        health="good",
        consecutive_failures=0,
        config_json=None,
        is_active=True,
    )
    return source


def _options(tmp_path, oss_config=None):
    return PipelineOptions(
        run_id="run_1",
        window_start=datetime(2026, 5, 25, 8, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
        hexo_posts_dir=tmp_path,
        oss_config=oss_config,
    )


@pytest.mark.asyncio
async def test_run_daily_pipeline_success_path_writes_digest_and_stats(tmp_path):
    session = FakeSession([_source()])
    stats_updates = []
    analyzer = FakeAnalyzer("今日安全情报以高危漏洞为主，应优先确认资产影响。")

    async def collector(sources, since=None):
        return [
            SourceFetchResult(
                source_id="security_nvd_cve",
                status="succeeded",
                items=[
                    RawItem(
                        source_id="security_nvd_cve",
                        title="High CVE",
                        canonical_url="https://nvd.nist.gov/vuln/detail/CVE-1",
                        content_text="details",
                        native_id="CVE-1",
                    )
                ],
                duration_s=1.0,
            )
        ]

    async def stats_updater(stats):
        stats_updates.append({**stats, "stage1": dict(stats.get("stage1", {})), "stage2": dict(stats.get("stage2", {}))})

    result = await run_daily_pipeline(
        session,
        analyzer,
        _options(tmp_path),
        collector=collector,
        stats_updater=stats_updater,
    )

    assert result.status == "succeeded"
    assert result.inserted_count == 1
    assert result.stats_json["stage1"] == {"total": 1, "succeeded": 1, "failed": 0}
    assert result.stats_json["stage2"] == {"total": 1, "succeeded": 1, "failed": 0}
    assert result.stats_json["digest"]["security"]["status"] == "succeeded"
    assert result.stats_json["digest"]["ai"]["status"] == "skipped"
    assert (tmp_path / "intelligence-security-2026-05-26.md").exists()
    digest_rows = [obj for obj in session.added if obj.__class__.__name__ == "Digest"]
    assert [digest.id for digest in digest_rows] == ["2026-05-26:security"]
    assert digest_rows[0].summary == "今日安全情报以高危漏洞为主，应优先确认资产影响。"
    assert "今日安全情报以高危漏洞为主，应优先确认资产影响。" in digest_rows[0].content_markdown
    assert analyzer.overview_calls == [
        (
            "security",
            [
                {
                    "title": "High CVE",
                    "category": "vulnerability",
                    "summary_zh": "High CVE 摘要",
                    "insight_score": 88,
                    "action_suggestion": "跟进",
                }
            ],
        )
    ]
    assert stats_updates[0]["sources"]["security_nvd_cve"]["status"] == "pending"
    assert any(update["stage1"] == {"total": 1, "succeeded": 1, "failed": 0} for update in stats_updates)
    assert stats_updates[-1]["retention_deleted"] == 0


@pytest.mark.asyncio
async def test_run_daily_pipeline_partial_when_one_source_fails(tmp_path):
    session = FakeSession([_source(), _source("ai_arxiv", "ai")])

    async def collector(sources, since=None):
        return [
            SourceFetchResult(
                source_id="security_nvd_cve",
                status="succeeded",
                items=[
                    RawItem(
                        source_id="security_nvd_cve",
                        title="High CVE",
                        canonical_url="https://nvd.nist.gov/vuln/detail/CVE-1",
                    )
                ],
                duration_s=1.0,
            ),
            SourceFetchResult(source_id="ai_arxiv", status="failed", error="source_timeout", items=[], duration_s=30.0),
        ]

    result = await run_daily_pipeline(session, FakeAnalyzer(), _options(tmp_path), collector=collector)

    assert result.status == "partial"
    assert result.stats_json["sources"]["ai_arxiv"]["error"] == "source_timeout"


@pytest.mark.asyncio
async def test_run_daily_pipeline_failed_when_hexo_write_fails(tmp_path):
    session = FakeSession([_source()])

    async def collector(sources, since=None):
        return [
            SourceFetchResult(
                source_id="security_nvd_cve",
                status="succeeded",
                items=[
                    RawItem(
                        source_id="security_nvd_cve",
                        title="High CVE",
                        canonical_url="https://nvd.nist.gov/vuln/detail/CVE-1",
                    )
                ],
                duration_s=1.0,
            )
        ]

    def failing_writer(artifact, posts_dir):
        raise OutputError("hexo_write_error", "no permission")

    result = await run_daily_pipeline(
        session,
        FakeAnalyzer(),
        _options(tmp_path),
        collector=collector,
        hexo_writer=failing_writer,
    )

    assert result.status == "failed"
    assert result.stats_json["digest"]["security"]["status"] == "failed"
    assert result.stats_json["digest"]["security"]["error"] == "hexo_write_error"


@pytest.mark.asyncio
async def test_run_daily_pipeline_oss_failure_does_not_fail_digest(tmp_path):
    session = FakeSession([_source()])
    oss_config = OSSConfig(endpoint="https://oss.example.com", bucket="bucket", access_key_id="id", access_key_secret="secret")

    async def collector(sources, since=None):
        return [
            SourceFetchResult(
                source_id="security_nvd_cve",
                status="succeeded",
                items=[
                    RawItem(
                        source_id="security_nvd_cve",
                        title="High CVE",
                        canonical_url="https://nvd.nist.gov/vuln/detail/CVE-1",
                    )
                ],
                duration_s=1.0,
            )
        ]

    def failing_oss(artifact, config):
        raise OutputError("oss_upload_error", "boom")

    result = await run_daily_pipeline(
        session,
        FakeAnalyzer(),
        _options(tmp_path, oss_config=oss_config),
        collector=collector,
        oss_uploader=failing_oss,
    )

    assert result.status == "succeeded"
    assert result.stats_json["digest"]["security"]["status"] == "succeeded"
    assert result.stats_json["digest"]["security"]["oss_url"] is None


@pytest.mark.asyncio
async def test_run_daily_pipeline_uses_template_overview_when_ai_overview_fails(tmp_path):
    session = FakeSession([_source()])

    async def collector(sources, since=None):
        return [
            SourceFetchResult(
                source_id="security_nvd_cve",
                status="succeeded",
                items=[
                    RawItem(
                        source_id="security_nvd_cve",
                        title="High CVE",
                        canonical_url="https://nvd.nist.gov/vuln/detail/CVE-1",
                    )
                ],
                duration_s=1.0,
            )
        ]

    result = await run_daily_pipeline(session, FakeAnalyzer(overview=None), _options(tmp_path), collector=collector)

    digest_rows = [obj for obj in session.added if obj.__class__.__name__ == "Digest"]
    assert result.status == "succeeded"
    assert digest_rows[0].summary == "今日共采集 1 条情报，高价值 1 条。"
