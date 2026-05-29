from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.analyzer import Stage1Outcome, Stage2Outcome
from src.models.item import Item
from src.pipeline.ingestion import (
    NormalizedItem,
    append_source_occurrence,
    recompute_confidence_after_dedup,
)


@dataclass(frozen=True)
class PersistResult:
    inserted: list[Item] = field(default_factory=list)
    duplicates: int = 0
    errors: int = 0


async def persist_normalized_items(
    session: AsyncSession,
    items: list[NormalizedItem],
    *,
    source_authority_by_id: dict[str, str],
) -> PersistResult:
    inserted: list[Item] = []
    duplicates = 0
    errors = 0

    for item in items:
        try:
            existing = await find_item_by_dedup_hash(session, item.dedup_hash)
            if existing:
                merge_duplicate_occurrence(existing, item, source_authority_by_id)
                duplicates += 1
                continue

            model = item_model_from_normalized(item)
            session.add(model)
            inserted.append(model)
        except Exception:
            errors += 1

    return PersistResult(inserted=inserted, duplicates=duplicates, errors=errors)


async def find_item_by_dedup_hash(session: AsyncSession, dedup_hash: str) -> Item | None:
    result = await session.execute(select(Item).where(Item.dedup_hash == dedup_hash))
    return result.scalar_one_or_none()


def item_model_from_normalized(item: NormalizedItem) -> Item:
    return Item(
        id=item.id,
        source_id=item.source_id,
        domain=item.domain,
        run_id=item.run_id,
        title=item.title,
        canonical_url=item.canonical_url,
        content_text=item.content_text,
        author=item.author,
        published_at=item.published_at,
        fetched_at=item.fetched_at,
        dedup_hash=item.dedup_hash,
        also_seen_in=item.also_seen_in,
        metadata_json=item.metadata_json,
        analysis_stage=0,
        credibility="unknown",
    )


def merge_duplicate_occurrence(
    existing: Item,
    duplicate: NormalizedItem,
    source_authority_by_id: dict[str, str],
) -> None:
    if existing.source_id == duplicate.source_id:
        return

    existing.also_seen_in = append_source_occurrence(
        existing.also_seen_in,
        source_id=duplicate.source_id,
        url=duplicate.canonical_url,
        seen_at=duplicate.fetched_at,
    )
    existing.confidence = recompute_confidence_after_dedup(
        analysis_stage=existing.analysis_stage,
        current_confidence=existing.confidence,
        source_authority=source_authority_by_id.get(existing.source_id, "regular"),
        also_seen_in=existing.also_seen_in,
    )


def source_authority_map(sources: list[Any]) -> dict[str, str]:
    return {source.id: source.authority for source in sources}


def apply_stage1_outcome(item: Item, outcome: Stage1Outcome) -> None:
    item.stage1_model = outcome.model
    item.stage1_provider = outcome.provider
    item.stage1_prompt_version = outcome.prompt_version
    item.stage1_analyzed_at = outcome.analyzed_at
    item.stage1_error = outcome.error

    if outcome.error or outcome.analysis is None:
        item.analysis_stage = 0
        return

    item.category = outcome.analysis.category
    item.tags = outcome.analysis.tags
    item.summary_zh = outcome.analysis.summary_zh
    item.insight_score = outcome.analysis.insight_score
    item.credibility = outcome.analysis.credibility
    item.expires_at = outcome.expires_at
    item.analysis_stage = 1


def apply_stage2_outcome(item: Item, outcome: Stage2Outcome) -> None:
    item.stage2_model = outcome.model
    item.stage2_provider = outcome.provider
    item.stage2_prompt_version = outcome.prompt_version
    item.stage2_analyzed_at = outcome.analyzed_at
    item.stage2_error = outcome.error

    if outcome.error or outcome.analysis is None:
        if item.analysis_stage < 1:
            item.analysis_stage = 1
        return

    item.recommendation_reason = outcome.analysis.recommendation_reason
    item.confidence = outcome.analysis.confidence
    item.trend_signal = outcome.analysis.trend_signal
    item.action_suggestion = outcome.analysis.action_suggestion
    item.analysis_stage = 2
