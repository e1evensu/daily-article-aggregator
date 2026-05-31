from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func as sa_func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.contracts import raise_api_error, success_envelope, visible_source_filters
from src.api.deps import get_db
from src.config import settings
from src.models.item import Item
from src.models.source import Source

router = APIRouter(tags=["sources"])


@router.get("/sources")
async def list_sources(request: Request, db: AsyncSession = Depends(get_db)):
    """List visible sources plus today's counts and sparkline data in batched queries."""
    # Batched to avoid an N+1 (the app is far from the DB; every round-trip is
    # ~1-6s over the cross-border link). One query for sources, one for today's
    # per-source counts, one for the spark histogram — 3 round-trips total
    # instead of 1 + 2 per source.
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    spark_days = settings.source_spark_days
    cutoff = now - timedelta(days=spark_days)

    sources = (
        await db.execute(
            select(Source)
            .where(*visible_source_filters())
            .order_by(Source.domain, Source.name)
        )
    ).scalars().all()

    today_rows = await db.execute(
        select(Item.source_id, sa_func.count())
        .where(Item.fetched_at >= today_start)
        .group_by(Item.source_id)
    )
    today_by_src = {sid: count for sid, count in today_rows}

    spark_rows = await db.execute(
        select(Item.source_id, cast(Item.fetched_at, Date), sa_func.count())
        .where(Item.fetched_at >= cutoff)
        .group_by(Item.source_id, cast(Item.fetched_at, Date))
    )
    spark_by_src: dict[str, dict] = {}
    for sid, day, count in spark_rows:
        spark_by_src.setdefault(sid, {})[day] = count

    data = build_source_views(sources, today_by_src, spark_by_src, now, spark_days)
    return success_envelope(data, request=request, total=len(data))


@router.get("/sources/{source_id}")
async def get_source(source_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Source).where(
            Source.id == source_id,
            *visible_source_filters(),
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise_api_error("not_found", "Source not found", 404)
    return success_envelope(await serialize_source(source, db), request=request)


def _spark_series(day_counts: dict, now: datetime, spark_days: int) -> list[int]:
    """Fill a dense sparkline series so missing days render as zero activity."""
    return [day_counts.get((now - timedelta(days=spark_days - 1 - i)).date(), 0) for i in range(spark_days)]


async def serialize_source(s: Source, db: AsyncSession) -> dict:
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
    return build_source_view(s, today_count or 0, _spark_series(day_counts, now, spark_days))


def build_source_view(s: Source, today_count: int, spark: list[int]) -> dict:
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


def build_source_views(
    sources: list[Source],
    today_by_src: dict[str, int],
    spark_by_src: dict[str, dict],
    now: datetime,
    spark_days: int,
) -> list[dict]:
    """Build source view models from batched counts and sparkline maps."""
    return [
        build_source_view(source, today_by_src.get(source.id, 0), _spark_series(spark_by_src.get(source.id, {}), now, spark_days))
        for source in sources
    ]
