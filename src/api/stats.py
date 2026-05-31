from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func as sa_func, case
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.contracts import success_envelope, visible_item_filters, visible_source_filters
from src.api.deps import get_db
from src.api.stats_helpers import histogram_from_bucket_counts, retention_counts_from_bucket_counts
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
    request: Request,
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

    today_filter = (
        (Item.fetched_at >= day_start)
        & (Item.fetched_at < day_end)
        & visible_item_filters()[0]
        & visible_item_filters()[1]
    )
    yesterday_filter = (
        (Item.fetched_at >= yesterday_start)
        & (Item.fetched_at < day_start)
        & visible_item_filters()[0]
        & visible_item_filters()[1]
    )

    item_rollup = await db.execute(
        select(
            Item.domain,
            sa_func.count().label("total"),
            sa_func.sum(case((Item.insight_score >= settings.stage2_threshold, 1), else_=0)).label("high_value"),
            sa_func.sum(case((Item.stage1_error.isnot(None), 1), else_=0)).label("failed"),
        )
        .where(today_filter)
        .group_by(Item.domain)
    )
    by_domain: dict[str, int] = {}
    total = 0
    high_value = 0
    failed = 0
    for domain, count, high_count, failed_count in item_rollup:
        by_domain[domain] = count
        total += count or 0
        high_value += high_count or 0
        failed += failed_count or 0

    yesterday_total = await db.scalar(
        select(sa_func.count()).select_from(Item).where(yesterday_filter)
    ) or 0

    source_result = await db.execute(
        select(
            sa_func.count().label("total"),
            sa_func.sum(case((Source.health == "good", 1), else_=0)).label("healthy"),
            sa_func.sum(case((Source.health == "degraded", 1), else_=0)).label("degraded"),
            sa_func.sum(case((Source.health == "disabled", 1), else_=0)).label("disabled"),
        )
        .select_from(Source)
        .where(*visible_source_filters(only_active=True))
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

    score_result = await db.execute(
        select(sa_func.floor(Item.insight_score / 5), sa_func.count())
        .where(today_filter, Item.insight_score.isnot(None))
        .group_by(sa_func.floor(Item.insight_score / 5))
    )
    bucket_counts = {int(bucket): count for bucket, count in score_result}

    return success_envelope(
        {
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
            "score_histogram": histogram_from_bucket_counts(bucket_counts),
            "retention_buckets": retention_counts_from_bucket_counts(bucket_counts),
            "category_counts": category_counts,
            "confidence_breakdown": confidence_breakdown,
        },
        request=request,
    )
