"""Sync the database with canonical sources from SOURCE_SEED_PATH."""
from __future__ import annotations

import asyncio

from src.collector.catalog import seed_candidate_sources
from src.db import async_session


async def main() -> int:
    """Seed or refresh canonical sources in the database from the configured catalog."""
    async with async_session() as session:
        count = await seed_candidate_sources(session)
        await session.commit()
    print(f"seeded {count} sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
