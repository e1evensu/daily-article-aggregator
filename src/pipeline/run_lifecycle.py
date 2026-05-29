from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.run import Run
from src.pipeline.run_stats import initial_run_stats

RUN_LOCK_NAME = settings.run_lock_name
STALE_RUN_TIMEOUT = timedelta(hours=settings.run_stale_timeout_hours)


@dataclass(frozen=True)
class LifecycleResult:
    status: str
    run: Run | None = None
    skipped_reason: str | None = None


async def acquire_run_lock(session: AsyncSession) -> bool:
    result = await session.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": RUN_LOCK_NAME})
    return result.scalar() == 1


async def release_run_lock(session: AsyncSession) -> None:
    await session.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": RUN_LOCK_NAME})


async def find_running_run(session: AsyncSession) -> Run | None:
    result = await session.execute(select(Run).where(Run.status == "running").order_by(Run.started_at.asc()).limit(1))
    return result.scalar_one_or_none()


async def find_latest_succeeded_run(session: AsyncSession) -> Run | None:
    result = await session.execute(
        select(Run).where(Run.status == "succeeded").order_by(Run.window_end.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def compute_run_window(session: AsyncSession, now: datetime) -> tuple[datetime, datetime]:
    latest = await find_latest_succeeded_run(session)
    window_end = _ensure_utc(now)
    if latest:
        return _ensure_utc(latest.window_end), window_end
    return window_end - timedelta(hours=settings.run_default_window_hours), window_end


def create_run_record(
    *,
    run_id: str,
    kind: str,
    window_start: datetime,
    window_end: datetime,
    started_at: datetime,
    source_ids: list[str],
) -> Run:
    return Run(
        id=run_id,
        kind=kind,
        status="running",
        window_start=window_start,
        window_end=window_end,
        started_at=started_at,
        finished_at=None,
        stats_json=initial_run_stats(source_ids),
        error_json=None,
    )


def mark_run_finished(run: Run, *, status: str, finished_at: datetime, stats_json: dict, error_json: dict | None = None) -> None:
    run.status = status
    run.finished_at = _ensure_utc(finished_at)
    run.stats_json = stats_json
    run.error_json = error_json


async def run_with_lifecycle(
    session: AsyncSession,
    *,
    run_id: str,
    kind: str,
    window_start: datetime,
    window_end: datetime,
    started_at: datetime,
    source_ids: list[str],
    runner: Callable[[Run], Awaitable[tuple[str, dict]]],
) -> LifecycleResult:
    locked = await acquire_run_lock(session)
    if not locked:
        return LifecycleResult(status="skipped", skipped_reason="lock_unavailable")

    try:
        existing = await find_running_run(session)
        if existing:
            if _ensure_utc(existing.started_at) < _ensure_utc(started_at) - STALE_RUN_TIMEOUT:
                mark_run_finished(
                    existing,
                    status="failed",
                    finished_at=started_at,
                    stats_json=existing.stats_json or {},
                    error_json={"reason": "stale_timeout"},
                )
            else:
                return LifecycleResult(status="skipped", run=existing, skipped_reason="run_already_running")

        run = create_run_record(
            run_id=run_id,
            kind=kind,
            window_start=window_start,
            window_end=window_end,
            started_at=started_at,
            source_ids=source_ids,
        )
        session.add(run)

        try:
            status, stats_json = await runner(run)
            mark_run_finished(run, status=status, finished_at=datetime.now(timezone.utc), stats_json=stats_json)
        except Exception as exc:
            mark_run_finished(
                run,
                status="failed",
                finished_at=datetime.now(timezone.utc),
                stats_json=run.stats_json or {},
                error_json={"reason": "unhandled_exception", "message": str(exc)},
            )
        return LifecycleResult(status=run.status, run=run)
    finally:
        await release_run_lock(session)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
