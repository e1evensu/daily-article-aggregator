from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.config import settings
from src.models.digest import Digest

router = APIRouter(tags=["digests"])


@router.get("/digests")
async def list_digests(
    domain: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Digest).order_by(Digest.date.desc()).limit(settings.api_recent_digests_limit)
    if domain and domain != "all":
        stmt = stmt.where(Digest.domain == domain)
    result = await db.execute(stmt)
    digests = result.scalars().all()
    return {"data": [_serialize(d) for d in digests], "meta": {"total": len(digests)}}


@router.get("/digests/latest")
async def latest_digest(
    domain: str = "security",
    format: str = "json",
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Digest).order_by(Digest.date.desc())
    if domain != "all":
        stmt = stmt.where(Digest.domain == domain)
    result = await db.execute(stmt.limit(1))
    digest = result.scalar_one_or_none()
    if not digest:
        return {"error": {"code": "not_found", "message": "No digest found"}, "meta": {}}
    if format == "markdown":
        return PlainTextResponse(digest.content_markdown, media_type="text/markdown")
    return {"data": _serialize(digest), "meta": {}}


@router.get("/digests/{date_str}")
async def get_digest(
    date_str: str,
    domain: str = "security",
    format: str = "json",
    db: AsyncSession = Depends(get_db),
):
    digest_id = f"{date_str}:{domain}"
    digest = await db.get(Digest, digest_id)
    if not digest:
        return {"error": {"code": "not_found", "message": "Digest not found"}, "meta": {}}
    if format == "markdown":
        return PlainTextResponse(digest.content_markdown, media_type="text/markdown")
    return {"data": _serialize(digest), "meta": {}}


def _serialize(d: Digest) -> dict:
    return {
        "id": d.id,
        "date": d.date.isoformat(),
        "domain": d.domain,
        "title": d.title,
        "summary": d.summary,
        "stats_json": d.stats_json,
        "highlights_json": d.highlights_json,
        "generated_at": d.generated_at.isoformat() if d.generated_at else None,
        "hexo_path": f"intelligence-{d.domain}-{d.date.isoformat()}.md",
        "oss_url": d.oss_url,
    }
