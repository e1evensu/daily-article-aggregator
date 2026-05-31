"""Prepare deferred source proposals beyond the Phase 1 catalog.

This script is intentionally conservative: it defaults to dry-run JSON output
and never marks sources approved. Phase 1 source approval must go through
``config/sources.json`` + ``verify_feeds.py``.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from src.collector.catalog import SourceCatalogEntry, as_source_model
from src.db import async_session

# (id, name, domain, url, authority)
DEFERRED_SOURCES = [
    # --- general: world news (English international) ---
    ("general_bbc_world", "BBC World", "general", "http://feeds.bbci.co.uk/news/world/rss.xml", "authoritative"),
    ("general_guardian_world", "The Guardian World", "general", "https://www.theguardian.com/world/rss", "authoritative"),
    ("general_nyt_world", "NYT World", "general", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "authoritative"),
    ("general_aljazeera", "Al Jazeera", "general", "https://www.aljazeera.com/xml/rss/all.xml", "authoritative"),
    # --- finance: US markets / tech ---
    ("finance_cnbc_markets", "CNBC Markets", "finance", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "authoritative"),
    ("finance_marketwatch", "MarketWatch Top", "finance", "http://feeds.marketwatch.com/marketwatch/topstories/", "authoritative"),
    # --- finance: crypto ---
    ("finance_coindesk", "CoinDesk", "finance", "https://www.coindesk.com/arc/outboundfeeds/rss/", "authoritative"),
    ("finance_cointelegraph", "Cointelegraph", "finance", "https://cointelegraph.com/rss", "authoritative"),
    # --- finance: macro / central banks ---
    ("finance_fed_press", "Federal Reserve Press", "finance", "https://www.federalreserve.gov/feeds/press_all.xml", "official"),
    ("finance_ecb_press", "ECB Press", "finance", "https://www.ecb.europa.eu/rss/press.xml", "official"),
    # --- curated analysts (HN-popularity OPML) — the 'learn from smart people' layer ---
    ("ai_simonwillison", "Simon Willison (AI/LLM)", "ai", "https://simonwillison.net/atom/everything/", "authoritative"),
    ("security_krebs", "Krebs on Security", "security", "https://krebsonsecurity.com/feed/", "authoritative"),
    ("general_pluralistic", "Pluralistic (Cory Doctorow)", "general", "https://pluralistic.net/feed/", "authoritative"),
    ("general_derekthompson", "Derek Thompson (Atlantic)", "general", "https://www.theatlantic.com/feed/author/derek-thompson/", "authoritative"),
    ("general_construction_physics", "Construction Physics", "general", "https://www.construction-physics.com/feed", "authoritative"),
]


def build_entries() -> list[SourceCatalogEntry]:
    return [
        SourceCatalogEntry(
            id=sid,
            name=name,
            domain=dom,
            type="rss",
            url=url,
            authority=auth,
            fetch_strategy="l1_rss",
            auth_mode="none",
            status="deferred",
            health="good",
            is_active=False,
        )
        for sid, name, dom, url, auth in DEFERRED_SOURCES
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List or store deferred non-Phase-1 source proposals")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="merge proposals into the database as deferred and inactive rows",
    )
    return parser.parse_args()


def entries_as_json(entries: list[SourceCatalogEntry]) -> str:
    """Serialize deferred source entries as formatted JSON for review."""
    return json.dumps([entry.__dict__ for entry in entries], indent=2, ensure_ascii=False)


async def apply_entries(entries: list[SourceCatalogEntry]) -> int:
    """Merge deferred source proposals into the database."""
    async with async_session() as s:
        for e in entries:
            await s.merge(as_source_model(e))
        await s.commit()
    return len(entries)


async def main() -> int:
    """Run the deferred-source proposal CLI."""
    args = parse_args()
    entries = build_entries()
    if not args.apply:
        print(entries_as_json(entries))
        print("dry-run: not writing database; use --apply to store deferred inactive proposals")
        return 0

    count = await apply_entries(entries)
    print(f"merged {count} deferred inactive source proposals")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
