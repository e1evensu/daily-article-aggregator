from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.item import Item


async def delete_expired_items(session: AsyncSession, now: datetime | None = None) -> int:
    cutoff = _ensure_utc(now or datetime.now(timezone.utc))
    result = await session.execute(delete(Item).where(Item.expires_at.isnot(None), Item.expires_at < cutoff))
    return int(result.rowcount or 0)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
