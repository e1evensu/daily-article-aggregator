from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.config import settings
from src.models.run import Run
from src.pipeline.run_stats import compute_progress

router = APIRouter(tags=["runs"])


@router.get("/runs")
async def list_runs(limit: int = settings.api_default_limit, db: AsyncSession = Depends(get_db)):
    limit = min(limit, settings.api_max_limit)
    result = await db.execute(select(Run).order_by(Run.started_at.desc()).limit(limit))
    runs = result.scalars().all()
    return {"data": [_serialize(r) for r in runs], "meta": {"total": len(runs)}}


@router.get("/runs/latest")
async def latest_run(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Run).order_by(Run.started_at.desc()).limit(1))
    run = result.scalar_one_or_none()
    if not run:
        return {"error": {"code": "not_found", "message": "No runs found"}, "meta": {}}
    return {"data": _serialize(run), "meta": {}}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(Run, run_id)
    if not run:
        return {"error": {"code": "not_found", "message": "Run not found"}, "meta": {}}
    return {"data": _serialize(run), "meta": {}}


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
