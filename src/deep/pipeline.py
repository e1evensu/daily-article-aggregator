"""Deep-analysis stage glue for the daily pipeline.

The daily run is fast; the pi Finder is slow and RPM-limited. So the pipeline
does NOT run pi inline — it only *enqueues* qualifying security items as
`deep_analyses` rows with status ``queued``. A separate worker
(``src.deep.worker``) drains the queue serially at pi's pace and fills in the
report. This keeps the daily pipeline quick and lets deep-dives run continuously
in the background.

Qualification proper (does the advisory name a repo + single fix commit?) is
deferred to the worker, which needs a GitHub round-trip anyway. Here we only
require that an item is a GitHub Security Advisory carrying a GHSA id.
"""
from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.deep_analysis import DeepAnalysis
from src.models.item import Item

GHSA_RE = re.compile(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}", re.I)
ARXIV_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf|html)/|arXiv:)?(\d{4}\.\d{4,5})(?:v\d+)?", re.I)


def extract_ghsa(item: Item) -> str | None:
    """Pull a GHSA id from an item (advisory URL, id, or title). None if absent."""
    for field in (item.canonical_url, item.id, item.title):
        if field:
            m = GHSA_RE.search(field)
            if m:
                # Normalize the prefix but keep the suffix lowercase — that's the
                # canonical GHSA form GitHub stores and its API expects.
                return "GHSA-" + m.group(0)[5:].lower()
    return None


def extract_arxiv_id(item: Item) -> str | None:
    """Pull an arXiv id from an item (arXiv URL or id). None if absent. Only
    matches when an arxiv.org/arXiv context is present, so plain `2512.07921`-
    looking numbers in unrelated URLs don't false-positive."""
    for field in (item.canonical_url, item.id):
        if not field:
            continue
        if "arxiv" in field.lower():
            m = ARXIV_RE.search(field)
            if m:
                return m.group(1)
    return None


async def enqueue_paper(
    session: AsyncSession, arxiv_id: str, *, item_id: str | None = None
) -> str | None:
    """Queue one AI paper for the deep-analysis worker (kind=paper_breakdown).
    Skips if a non-failed row already exists. Returns the id if enqueued."""
    existing = await session.execute(
        select(DeepAnalysis.id).where(
            DeepAnalysis.id == arxiv_id, DeepAnalysis.status != "failed"
        )
    )
    if existing.first():
        return None
    stmt = mysql_insert(DeepAnalysis).values(
        id=arxiv_id, subject=arxiv_id, item_id=item_id, kind="paper_breakdown", status="queued"
    )
    stmt = stmt.on_duplicate_key_update(status="queued", item_id=stmt.inserted.item_id)
    await session.execute(stmt)
    return arxiv_id


def select_candidates(items: Iterable[Item], *, min_score: int, limit: int) -> list[tuple[Item, str]]:
    """Security-domain items that carry a GHSA id and clear the score floor,
    highest insight_score first, capped at `limit`."""
    scored: list[tuple[int, Item, str]] = []
    for item in items:
        if item.domain != "security":
            continue
        score = item.insight_score or 0
        if score < min_score:
            continue
        ghsa = extract_ghsa(item)
        if ghsa:
            scored.append((score, item, ghsa))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [(item, ghsa) for _, item, ghsa in scored[:limit]]


async def enqueue_candidates(
    session: AsyncSession, items: Iterable[Item], *, min_score: int, limit: int
) -> list[str]:
    """Insert `queued` deep_analyses rows for qualifying items. Skips subjects
    that already have a row in any non-failed state (don't re-queue a done or
    in-flight analysis). Returns the GHSA ids newly enqueued."""
    candidates = select_candidates(items, min_score=min_score, limit=limit)
    if not candidates:
        return []

    subjects = [ghsa for _, ghsa in candidates]
    existing = await session.execute(
        select(DeepAnalysis.id).where(
            DeepAnalysis.id.in_(subjects), DeepAnalysis.status != "failed"
        )
    )
    skip = {row[0] for row in existing.all()}

    enqueued: list[str] = []
    for item, ghsa in candidates:
        if ghsa in skip:
            continue
        stmt = mysql_insert(DeepAnalysis).values(
            id=ghsa, subject=ghsa, item_id=item.id, kind="vuln_rca", status="queued"
        )
        # If a failed row exists, retry it: reset to queued and relink the item.
        stmt = stmt.on_duplicate_key_update(
            status="queued", item_id=stmt.inserted.item_id
        )
        await session.execute(stmt)
        enqueued.append(ghsa)
    return enqueued
