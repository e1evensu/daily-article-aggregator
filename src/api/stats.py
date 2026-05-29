from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func as sa_func, case
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.stats_helpers import retention_bucket_counts, score_histogram
from src.config import settings
from src.models.item import Item
from src.models.source import Source

router = APIRouter(tags=["stats"])

CATEGORY_VALUES = [
    "vulnerability", "exploit", "research", "product",
    "engineering", "tool", "incident", "discussion", "other",
]


@router.get("/stats")
async def get_stats(
    date: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    if date:
        target = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    else:
        target = now
    day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    yesterday_start = day_start - timedelta(days=1)

    today_filter = (Item.fetched_at >= day_start) & (Item.fetched_at < day_end)
    yesterday_filter = (Item.fetched_at >= yesterday_start) & (Item.fetched_at < day_start)

    total = await db.scalar(select(sa_func.count()).select_from(Item).where(today_filter)) or 0

    domain_result = await db.execute(
        select(Item.domain, sa_func.count()).where(today_filter).group_by(Item.domain)
    )
    by_domain = {r[0]: r[1] for r in domain_result}

    high_value = await db.scalar(
        select(sa_func.count()).select_from(Item).where(today_filter, Item.insight_score >= settings.stage2_threshold)
    ) or 0

    failed = await db.scalar(
        select(sa_func.count()).select_from(Item).where(today_filter, Item.stage1_error.isnot(None))
    ) or 0

    yesterday_total = await db.scalar(
        select(sa_func.count()).select_from(Item).where(yesterday_filter)
    ) or 0

    source_result = await db.execute(
        select(
            sa_func.count().label("total"),
            sa_func.sum(case((Source.health == "good", 1), else_=0)).label("healthy"),
            sa_func.sum(case((Source.health == "degraded", 1), else_=0)).label("degraded"),
            sa_func.sum(case((Source.health == "disabled", 1), else_=0)).label("disabled"),
        ).select_from(Source).where(Source.is_active == True)
    )
    sr = source_result.one()

    cat_result = await db.execute(
        select(Item.category, sa_func.count()).where(today_filter, Item.category.isnot(None)).group_by(Item.category)
    )
    category_counts = {r[0]: r[1] for r in cat_result}

    conf_result = await db.execute(
        select(Item.confidence, sa_func.count()).where(today_filter, Item.confidence.isnot(None)).group_by(Item.confidence)
    )
    confidence_breakdown = {r[0]: r[1] for r in conf_result}

    score_result = await db.execute(select(Item.insight_score).where(today_filter, Item.insight_score.isnot(None)))
    scores = [row[0] for row in score_result]

    return {
        "data": {
            "date": day_start.date().isoformat(),
            "items": {
                "total": total,
                "by_domain": by_domain,
                "high_value": high_value,
                "failed_analyses": failed,
                "delta_vs_yesterday": total - yesterday_total,
            },
            "sources": {
                "total": sr.total or 0,
                "healthy": sr.healthy or 0,
                "degraded": sr.degraded or 0,
                "disabled": sr.disabled or 0,
            },
            "score_histogram": score_histogram(scores),
            "retention_buckets": retention_bucket_counts(scores),
            "category_counts": category_counts,
            "confidence_breakdown": confidence_breakdown,
        },
        "meta": {},
    }
