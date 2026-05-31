"""Deep-analysis queue drainer.

Picks up `deep_analyses` rows the daily pipeline left in status ``queued`` and
runs the pi Finder against each, serially (pi is RPM-limited — never parallel).
Qualifies the advisory (explicit repo + single fix commit), checks out the
vulnerable state, traces source->sink, and stores the report linked back to the
originating item.

Run as a cron/systemd job, decoupled from the daily pipeline:

    python3 -m src.deep.worker            # drain all queued (serial)
    python3 -m src.deep.worker --max 3    # at most 3 this invocation
    python3 -m src.deep.worker --retry    # also re-run previously failed rows

Outcomes per row: ok / empty (all providers returned nothing) /
not_qualified (no repo+fix commit) / failed (crashed; eligible for --retry).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db import async_session
from src.deep import finder, store
from src.models.deep_analysis import DeepAnalysis

# finder reads GITHUB_TOKEN straight from the environment; seed it from settings
# so the worker works under cron without an exported env.
if settings.github_token and not os.environ.get("GITHUB_TOKEN"):
    os.environ["GITHUB_TOKEN"] = settings.github_token

# The DB lives in CN (114); the EU(38)->CN link can wedge a query with no
# server-side statement timeout. Bound every DB op so a hung cross-border call
# can never freeze the daily drain. Generous (small queries) but finite.
DB_OP_TIMEOUT = float(os.environ.get("DEEP_DB_OP_TIMEOUT", "60"))
WORKER_ID = os.environ.get("DEEP_WORKER_ID") or socket.gethostname()
STALE_CLAIM_TIMEOUT = timedelta(hours=settings.deep_analysis_stale_claim_timeout_hours)


class DBTimeout(Exception):
    pass


async def _db(coro, label: str):
    """Run one DB coroutine under a hard timeout so cross-border stalls fail fast."""
    try:
        return await asyncio.wait_for(coro, timeout=DB_OP_TIMEOUT)
    except asyncio.TimeoutError as e:
        raise DBTimeout(f"DB op timed out after {DB_OP_TIMEOUT}s: {label}") from e


async def _reset_stale_running(session: AsyncSession, now: datetime | None = None) -> int:
    """Return wedged running jobs to failed so later drains can retry them explicitly."""
    cutoff = (now or datetime.now(timezone.utc)) - STALE_CLAIM_TIMEOUT
    result = await _db(
        session.execute(
            update(DeepAnalysis)
            .where(
                DeepAnalysis.status == "running",
                DeepAnalysis.claimed_at.is_not(None),
                DeepAnalysis.claimed_at < cutoff,
            )
            .values(
                status="failed",
                claimed_at=None,
                worker_id=None,
            )
        ),
        "reset_stale_running",
    )
    await _db(session.commit(), "commit_reset_stale_running")
    return result.rowcount or 0


async def _claim_queued(session: AsyncSession, retry: bool, max_n: int | None) -> list[tuple[str, str | None, str]]:
    """Claim queued deep-analysis rows for this drain pass.

    The initial select is only a candidate list. Each row is then claimed with
    a conditional update on the expected status, so concurrent workers cannot
    both transition the same row to ``running``.
    """
    states = ["queued", "failed"] if retry else ["queued"]
    q = (
        select(DeepAnalysis.id, DeepAnalysis.item_id, DeepAnalysis.kind)
        .where(DeepAnalysis.status.in_(states))
        .order_by(DeepAnalysis.created_at.asc())
    )
    if max_n:
        q = q.limit(max_n)
    rows = await _db(session.execute(q), "claim_queued")
    claimed: list[tuple[str, str | None, str]] = []
    claimed_at = datetime.now(timezone.utc)
    for subject, item_id, kind in rows.all():
        result = await _db(
            session.execute(
                update(DeepAnalysis)
                .where(DeepAnalysis.id == subject, DeepAnalysis.status.in_(states))
                .values(
                    status="running",
                    claimed_at=claimed_at,
                    worker_id=WORKER_ID,
                    attempt_count=DeepAnalysis.attempt_count + 1,
                )
            ),
            f"claim_status({subject})",
        )
        if result.rowcount == 1:
            claimed.append((subject, item_id, kind or "vuln_rca"))
    await _db(session.commit(), "commit_claims")
    return claimed


async def _set_status(session: AsyncSession, subject: str, status: str) -> None:
    """Persist one deep-analysis row status transition immediately."""
    await _db(
        session.execute(
            update(DeepAnalysis)
            .where(DeepAnalysis.id == subject)
            .values(
                status=status,
                claimed_at=None,
                worker_id=None,
            )
        ),
        f"set_status({subject}={status})",
    )
    await _db(session.commit(), f"commit_status({subject})")


async def process_one(session: AsyncSession, subject: str, item_id: str | None, kind: str) -> str:
    """Run one queued deep-analysis job and persist its resulting report or status."""
    runner = finder.deep_analyze_paper if kind == "paper_breakdown" else finder.deep_analyze_advisory
    try:
        # pi is a blocking subprocess; keep the event loop free.
        meta = await asyncio.to_thread(runner, subject)
    except Exception as exc:  # noqa: BLE001
        print(f"[{subject}] crashed: {exc}")
        await _set_status(session, subject, "failed")
        return "failed"

    if meta is None:
        await _set_status(session, subject, "not_qualified")
        return "not_qualified"

    report_path = Path(meta.get("report_path", ""))
    # The pi report is already safe on disk; if the cross-border ingest hangs we
    # don't lose it — `python -m src.deep.store ingest-pending` can pick it up.
    if report_path.exists():
        await _db(store.ingest_file(report_path, item_id=item_id), f"ingest_file({subject})")
    else:  # pi produced nothing on disk; persist the meta we have
        await _db(store.ingest_meta(meta, meta.get("report_md", ""), item_id=item_id),
                  f"ingest_meta({subject})")
    status = meta.get("status", "ok")
    print(f"[{subject}] {status} via {meta.get('model')} ({meta.get('report_len', 0)} chars)")
    return status


async def drain(retry: bool = False, max_n: int | None = None) -> dict[str, int]:
    """Drain queued deep-analysis jobs serially and return an outcome tally."""
    async with async_session() as session:
        reset = await _reset_stale_running(session)
        queued = await _claim_queued(session, retry, max_n)
    if not queued:
        print("queue empty")
        return {"reset_stale": reset} if reset else {}

    print(f"draining {len(queued)} item(s) serially ...")
    tally: dict[str, int] = {"reset_stale": reset} if reset else {}
    for subject, item_id, kind in queued:
        # Fresh session per item: each pi run can take many minutes; don't hold a
        # cross-border connection open the whole time.
        try:
            async with async_session() as session:
                outcome = await process_one(session, subject, item_id, kind)
        except DBTimeout as e:
            # The CN link is wedged — no point hammering the rest of the batch.
            # Any finished pi report is safe on disk for `store ingest-pending`.
            print(f"[{subject}] {e}; aborting drain (report, if any, is on disk)")
            tally["db_timeout"] = tally.get("db_timeout", 0) + 1
            break
        tally[outcome] = tally.get(outcome, 0) + 1
    print("done:", ", ".join(f"{k}={v}" for k, v in tally.items()))
    return tally


def main() -> None:
    """Run the deep-analysis worker CLI."""
    ap = argparse.ArgumentParser(description="Deep-analysis queue drainer")
    ap.add_argument("--max", type=int, default=None, help="cap items this run")
    ap.add_argument("--retry", action="store_true", help="also re-run failed rows")
    a = ap.parse_args()
    asyncio.run(drain(retry=a.retry, max_n=a.max))


if __name__ == "__main__":
    main()
