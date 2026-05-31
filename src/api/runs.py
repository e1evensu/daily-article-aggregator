from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.contracts import raise_api_error, success_envelope
from src.api.deps import get_db
from src.config import settings
from src.models.run import Run
from src.pipeline.run_stats import compute_progress

router = APIRouter(tags=["runs"])


@router.get("/runs")
async def list_runs(
    request: Request,
    limit: int = settings.api_default_limit,
    db: AsyncSession = Depends(get_db),
):
    """List recent pipeline runs with computed progress for the dashboard."""
    limit = min(limit, settings.api_max_limit)
    result = await db.execute(select(Run).order_by(Run.started_at.desc()).limit(limit))
    runs = result.scalars().all()
    return success_envelope([_serialize(r) for r in runs], request=request, total=len(runs))


@router.get("/runs/latest")
async def latest_run(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Run).order_by(Run.started_at.desc()).limit(1))
    run = result.scalar_one_or_none()
    if not run:
        raise_api_error("not_found", "No runs found", 404)
    return success_envelope(_serialize(run), request=request)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    run = await db.get(Run, run_id)
    if not run:
        raise_api_error("not_found", "Run not found", 404)
    return success_envelope(_serialize(run), request=request)


def _serialize(r: Run) -> dict:
    return {
        "id": r.id,
        "kind": r.kind,
        "status": r.status,
        "window_start": r.window_start.isoformat() if r.window_start else None,
        "window_end": r.window_end.isoformat() if r.window_end else None,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "progress": compute_progress(r.stats_json),
        "stats_json": r.stats_json,
    }
