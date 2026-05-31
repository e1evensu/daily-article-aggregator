from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.contracts import allowed_domains, raise_api_error, success_envelope
from src.api.deps import get_db
from src.config import settings
from src.models.digest import Digest

router = APIRouter(tags=["digests"])


@router.get("/digests")
async def list_digests(
    request: Request,
    domain: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List recent digests for the configured domains, optionally filtered by domain."""
    stmt = select(Digest).where(Digest.domain.in_(allowed_domains())).order_by(Digest.date.desc()).limit(
        settings.api_recent_digests_limit
    )
    if domain and domain != "all":
        stmt = stmt.where(Digest.domain == domain)
    result = await db.execute(stmt)
    digests = result.scalars().all()
    return success_envelope([_serialize(d) for d in digests], request=request, total=len(digests))


@router.get("/digests/latest")
async def latest_digest(
    request: Request,
    domain: str = "security",
    format: str = "json",
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Digest).where(Digest.domain.in_(allowed_domains())).order_by(Digest.date.desc())
    if domain != "all":
        stmt = stmt.where(Digest.domain == domain)
    result = await db.execute(stmt.limit(1))
    digest = result.scalar_one_or_none()
    if not digest:
        raise_api_error("not_found", "No digest found", 404)
    if format == "markdown":
        return PlainTextResponse(digest.content_markdown, media_type="text/markdown")
    return success_envelope(_serialize(digest), request=request)


@router.get("/digests/{date_str}")
async def get_digest(
    date_str: str,
    request: Request,
    domain: str = "security",
    format: str = "json",
    db: AsyncSession = Depends(get_db),
):
    digest_id = f"{date_str}:{domain}"
    if domain not in allowed_domains():
        raise_api_error("not_found", "Digest not found", 404)
    digest = await db.get(Digest, digest_id)
    if not digest:
        raise_api_error("not_found", "Digest not found", 404)
    if format == "markdown":
        return PlainTextResponse(digest.content_markdown, media_type="text/markdown")
    return success_envelope(_serialize(digest), request=request)


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
