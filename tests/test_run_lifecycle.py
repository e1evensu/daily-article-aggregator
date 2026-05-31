from datetime import datetime, timedelta, timezone

import pytest

from src.models.run import Run
from src.pipeline.run_lifecycle import (
    RUN_LOCK_NAME,
    compute_run_window,
    create_run_record,
    mark_run_finished,
    run_with_lifecycle,
)


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        """Return the fake scalar value for advisory-lock queries."""
        return self.value

    def scalar_one_or_none(self):
        """Return the fake scalar value for run lookups."""
        return self.value


class FakeSession:
    def __init__(self, *, lock_value=1, running_run=None, latest_succeeded_run=None):
        self.lock_value = lock_value
        self.running_run = running_run
        self.latest_succeeded_run = latest_succeeded_run
        self.added = []
        self.lock_calls = []

    async def execute(self, statement, params=None):
        """Serve fake advisory-lock and run queries for lifecycle tests."""
        sql = str(statement)
        if "GET_LOCK" in sql:
            self.lock_calls.append(("get", params["name"]))
            return FakeScalarResult(self.lock_value)
        if "RELEASE_LOCK" in sql:
            self.lock_calls.append(("release", params["name"]))
            return FakeScalarResult(1)
        if "FROM runs" in sql and "runs.status = :status_1" in sql:
            params_text = str(statement.compile().params)
            if "succeeded" in params_text:
                return FakeScalarResult(self.latest_succeeded_run)
            return FakeScalarResult(self.running_run)
        return FakeScalarResult(None)

    def add(self, value):
        """Record added run rows."""
        self.added.append(value)


def test_create_and_finish_run_record():
    started_at = datetime(2026, 5, 26, 8, tzinfo=timezone.utc)
    run = create_run_record(
        run_id="run_1",
        kind="daily",
        window_start=started_at - timedelta(hours=24),
        window_end=started_at,
        started_at=started_at,
        source_ids=["security_nvd_cve"],
    )

    assert run.id == "run_1"
    assert run.status == "running"
    assert run.stats_json["sources"]["security_nvd_cve"]["status"] == "pending"

    mark_run_finished(run, status="succeeded", finished_at=started_at, stats_json={"done": True})

    assert run.status == "succeeded"
    assert run.finished_at == started_at
    assert run.stats_json == {"done": True}


@pytest.mark.asyncio
async def test_compute_run_window_uses_latest_success_window_end():
    now = datetime(2026, 5, 26, 8, tzinfo=timezone.utc)
    latest = Run(
        id="run_success",
        kind="daily",
        status="succeeded",
        window_start=now - timedelta(days=2),
        window_end=now - timedelta(hours=6),
        started_at=now - timedelta(hours=7),
        stats_json={},
    )
    session = FakeSession(latest_succeeded_run=latest)

    window_start, window_end = await compute_run_window(session, now)

    assert window_start == now - timedelta(hours=6)
    assert window_end == now


@pytest.mark.asyncio
async def test_compute_run_window_defaults_to_24h_without_successful_run():
    now = datetime(2026, 5, 26, 8, tzinfo=timezone.utc)
    session = FakeSession()

    window_start, window_end = await compute_run_window(session, now)

    assert window_start == now - timedelta(hours=24)
    assert window_end == now


@pytest.mark.asyncio
async def test_run_with_lifecycle_skips_when_lock_unavailable():
    session = FakeSession(lock_value=0)
    called = False

    async def runner(run):
        nonlocal called
        called = True
        return "succeeded", {}

    result = await run_with_lifecycle(
        session,
        run_id="run_1",
        kind="daily",
        window_start=datetime(2026, 5, 25, tzinfo=timezone.utc),
        window_end=datetime(2026, 5, 26, tzinfo=timezone.utc),
        started_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
        source_ids=[],
        runner=runner,
    )

    assert result.status == "skipped"
    assert result.skipped_reason == "lock_unavailable"
    assert called is False
    assert session.lock_calls == [("get", RUN_LOCK_NAME)]


@pytest.mark.asyncio
async def test_run_with_lifecycle_skips_when_recent_run_is_running_and_releases_lock():
    now = datetime(2026, 5, 26, 8, tzinfo=timezone.utc)
    running = Run(
        id="run_existing",
        kind="daily",
        status="running",
        window_start=now - timedelta(hours=1),
        window_end=now,
        started_at=now - timedelta(hours=1),
        stats_json={},
    )
    session = FakeSession(running_run=running)

    async def runner(run):
        raise AssertionError("runner should not be called")

    result = await run_with_lifecycle(
        session,
        run_id="run_new",
        kind="daily",
        window_start=now - timedelta(hours=24),
        window_end=now,
        started_at=now,
        source_ids=[],
        runner=runner,
    )

    assert result.status == "skipped"
    assert result.run is running
    assert result.skipped_reason == "run_already_running"
    assert session.lock_calls == [("get", RUN_LOCK_NAME), ("release", RUN_LOCK_NAME)]


@pytest.mark.asyncio
async def test_run_with_lifecycle_marks_stale_run_failed_then_creates_new_run():
    now = datetime(2026, 5, 26, 8, tzinfo=timezone.utc)
    stale = Run(
        id="run_stale",
        kind="daily",
        status="running",
        window_start=now - timedelta(days=1),
        window_end=now - timedelta(hours=13),
        started_at=now - timedelta(hours=13),
        stats_json={"old": True},
    )
    session = FakeSession(running_run=stale)

    async def runner(run):
        return "succeeded", {"new": True}

    result = await run_with_lifecycle(
        session,
        run_id="run_new",
        kind="daily",
        window_start=now - timedelta(hours=24),
        window_end=now,
        started_at=now,
        source_ids=["security_nvd_cve"],
        runner=runner,
    )

    assert stale.status == "failed"
    assert stale.error_json == {"reason": "stale_timeout"}
    assert result.status == "succeeded"
    assert result.run.id == "run_new"
    assert result.run.stats_json == {"new": True}
    assert [run.id for run in session.added] == ["run_new"]


@pytest.mark.asyncio
async def test_run_with_lifecycle_marks_new_run_failed_on_exception():
    now = datetime(2026, 5, 26, 8, tzinfo=timezone.utc)
    session = FakeSession()

    async def runner(run):
        raise RuntimeError("boom")

    result = await run_with_lifecycle(
        session,
        run_id="run_1",
        kind="daily",
        window_start=now - timedelta(hours=24),
        window_end=now,
        started_at=now,
        source_ids=[],
        runner=runner,
    )

    assert result.status == "failed"
    assert result.run.status == "failed"
    assert result.run.error_json["reason"] == "unhandled_exception"
    assert "boom" in result.run.error_json["message"]
