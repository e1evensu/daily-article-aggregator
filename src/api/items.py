from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.contracts import decode_score_cursor, encode_score_cursor, raise_api_error, success_envelope
from src.api.deps import get_db, require_api_token
from src.config import settings
from src.models.item import Item

router = APIRouter(tags=["items"], dependencies=[Depends(require_api_token)])


@router.get("/items")
async def list_items(
    request: Request,
    domain: str | None = None,
    category: str | None = None,
    min_score: int | None = None,
    analysis_stage: int | None = None,
    confidence: str | None = None,
    trend_signal: str | None = None,
    source_id: str | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=settings.api_default_limit, le=settings.api_max_limit),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Item)

    if domain and domain != "all":
        stmt = stmt.where(Item.domain == domain)
    if category:
        stmt = stmt.where(Item.category == category)
    if min_score is not None:
        stmt = stmt.where(Item.insight_score >= min_score)
    if analysis_stage is not None:
        stmt = stmt.where(Item.analysis_stage == analysis_stage)
    if confidence:
        stmt = stmt.where(Item.confidence == confidence)
    if trend_signal:
        stmt = stmt.where(Item.trend_signal == trend_signal)
    if source_id:
        stmt = stmt.where(Item.source_id == source_id)
    if q:
        stmt = stmt.where(text("MATCH(title, summary_zh, content_text) AGAINST(:q IN BOOLEAN MODE)")).params(q=q)
    if since:
        stmt = stmt.where(Item.published_at >= _parse_iso_datetime(since, "since"))
    if until:
        stmt = stmt.where(Item.published_at <= _parse_iso_datetime(until, "until"))
    if cursor:
        score_cursor = decode_score_cursor(cursor)
        stmt = stmt.where(
            or_(
                Item.insight_score < score_cursor.insight_score,
                (Item.insight_score == score_cursor.insight_score) & (Item.id > score_cursor.item_id),
            )
        )

    if q:
        stmt = stmt.order_by(text("MATCH(title, summary_zh, content_text) AGAINST(:q2 IN BOOLEAN MODE) DESC")).params(q2=q)
    stmt = stmt.order_by(Item.insight_score.desc(), Item.id.asc())
    stmt = stmt.limit(limit + 1)

    result = await db.execute(stmt)
    items = result.scalars().all()
    page_items = items[:limit]
    next_cursor = None
    if len(items) > limit and page_items:
        last = page_items[-1]
        next_cursor = encode_score_cursor(last.insight_score, last.id)

    return success_envelope(
        [_serialize_item(i) for i in page_items],
        request=request,
        next_cursor=next_cursor,
        total=len(page_items),
    )


@router.get("/items/{item_id}")
async def get_item(item_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    item = await db.get(Item, item_id)
    if not item:
        raise_api_error("not_found", "Item not found", 404)
    return success_envelope(_serialize_item(item), request=request)


def _serialize_item(item: Item) -> dict:
    return {
        "id": item.id,
        "source_id": item.source_id,
        "domain": item.domain,
        "title": item.title,
        "canonical_url": item.canonical_url,
        "author": item.author,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "fetched_at": item.fetched_at.isoformat() if item.fetched_at else None,
        "also_seen_in": item.also_seen_in,
        "category": item.category,
        "tags": item.tags,
        "summary_zh": item.summary_zh,
        "insight_score": item.insight_score,
        "credibility": item.credibility,
        "confidence": item.confidence,
        "trend_signal": item.trend_signal,
        "recommendation_reason": item.recommendation_reason,
        "action_suggestion": item.action_suggestion,
        "analysis_stage": item.analysis_stage,
        "stage1_model": item.stage1_model,
        "stage1_provider": item.stage1_provider,
        "stage1_prompt_version": item.stage1_prompt_version,
        "stage1_analyzed_at": item.stage1_analyzed_at.isoformat() if item.stage1_analyzed_at else None,
        "stage2_model": item.stage2_model,
        "stage2_provider": item.stage2_provider,
        "stage2_prompt_version": item.stage2_prompt_version,
        "stage2_analyzed_at": item.stage2_analyzed_at.isoformat() if item.stage2_analyzed_at else None,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
    }


def _parse_iso_datetime(value: str, name: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise_api_error("invalid_param", f"{name} must be an ISO timestamp", 400)
        raise AssertionError("unreachable")
