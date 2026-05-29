from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func as sa_func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.contracts import raise_api_error
from src.api.deps import get_db
from src.config import settings
from src.models.item import Item
from src.models.source import Source

router = APIRouter(tags=["sources"])


@router.get("/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).order_by(Source.domain, Source.name))
    sources = result.scalars().all()
    data = []
    for s in sources:
        data.append(await _serialize(s, db))
    return {"data": data, "meta": {"total": len(data)}}


@router.get("/sources/{source_id}")
async def get_source(source_id: str, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, source_id)
    if not source:
        return {"error": {"code": "not_found", "message": "Source not found"}, "meta": {}}
    return {"data": await _serialize(source, db), "meta": {}}


@router.put("/sources/{source_id}")
async def upsert_source(source_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, source_id)
    if source is None:
        source = Source(id=source_id)
        db.add(source)

    _apply_source_payload(source, payload)
    await db.flush()
    return {"data": await _serialize(source, db), "meta": {}}


@router.patch("/sources/{source_id}")
async def update_source(source_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, source_id)
    if not source:
        raise_api_error("not_found", "Source not found", 404)

    _apply_source_payload(source, payload, partial=True)
    await db.flush()
    return {"data": await _serialize(source, db), "meta": {}}


async def _serialize(s: Source, db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    today_count = await db.scalar(
        select(sa_func.count()).select_from(Item).where(Item.source_id == s.id, Item.fetched_at >= today_start)
    )

    spark_days = settings.source_spark_days
    cutoff = now - timedelta(days=spark_days)
    spark_result = await db.execute(
        select(cast(Item.fetched_at, Date), sa_func.count())
        .where(Item.source_id == s.id, Item.fetched_at >= cutoff)
        .group_by(cast(Item.fetched_at, Date))
        .order_by(cast(Item.fetched_at, Date))
    )
    day_counts = {row[0]: row[1] for row in spark_result}
    spark = []
    for i in range(spark_days):
        d = (now - timedelta(days=spark_days - 1 - i)).date()
        spark.append(day_counts.get(d, 0))

    return {
        "id": s.id,
        "name": s.name,
        "domain": s.domain,
        "type": s.type,
        "url": s.url,
        "authority": s.authority,
        "status": s.status,
        "health": s.health,
        "consecutive_failures": s.consecutive_failures,
        "is_active": s.is_active,
        "last_fetch_at": s.last_fetch_at.isoformat() if s.last_fetch_at else None,
        "last_fetch_status": s.last_fetch_status,
        "today_items": today_count or 0,
        "spark": spark,
    }


def _apply_source_payload(source: Source, payload: dict, *, partial: bool = False) -> None:
    required = ("name", "domain", "type", "url", "fetch_strategy", "authority")
    if not partial:
        missing = [field for field in required if field not in payload]
        if missing:
            raise_api_error("invalid_param", f"Missing source fields: {', '.join(missing)}", 400)

    for field in required:
        if field in payload:
            value = payload[field]
            if not isinstance(value, str) or not value.strip():
                raise_api_error("invalid_param", f"{field} must be a non-empty string", 400)
            setattr(source, field, value.strip())

    for field in ("auth_mode", "status", "health"):
        if field in payload:
            value = payload[field]
            if not isinstance(value, str) or not value.strip():
                raise_api_error("invalid_param", f"{field} must be a non-empty string", 400)
            setattr(source, field, value.strip())

    if "is_active" in payload:
        source.is_active = bool(payload["is_active"])
    if "config_json" in payload:
        config_json = payload["config_json"]
        if config_json is not None and not isinstance(config_json, dict):
            raise_api_error("invalid_param", "config_json must be an object", 400)
        source.config_json = config_json
