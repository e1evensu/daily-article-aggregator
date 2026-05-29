from typing import AsyncGenerator

from fastapi import Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.contracts import raise_api_error
from src.config import settings


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    from src.db import async_session

    async with async_session() as session:
        yield session


async def require_api_token(authorization: str | None = Header(default=None)) -> None:
    if not settings.api_token:
        return
    expected = f"Bearer {settings.api_token}"
    if authorization != expected:
        raise_api_error("unauthorized", "Invalid API token", 401)
