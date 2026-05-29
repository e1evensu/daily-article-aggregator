from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.ai.contracts import derive_confidence
from src.collector.base import RawItem, canonicalize_url


class NormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedItem:
    id: str
    source_id: str
    domain: str
    run_id: str | None
    title: str
    canonical_url: str
    content_text: str | None
    author: str | None
    published_at: datetime | None
    fetched_at: datetime
    dedup_hash: str
    also_seen_in: list[dict[str, Any]] | None
    metadata_json: dict[str, Any] | None


def normalize_raw_item(
    raw: RawItem,
    *,
    source_domain: str,
    run_id: str | None = None,
    fetched_at: datetime | None = None,
    now: datetime | None = None,
) -> NormalizedItem:
    now = _ensure_utc(now or datetime.now(timezone.utc))
    fetched_at = _ensure_utc(fetched_at or now)
    published_at = _ensure_utc(raw.published_at) if raw.published_at else None

    title = raw.title.strip()
    content_text = raw.content_text.strip() if raw.content_text else None
    if not title and not content_text:
        raise NormalizationError("title or content_text is required")
    if published_at and published_at > now + timedelta(days=7):
        raise NormalizationError("published_at is more than 7 days in the future")

    canonical_url = canonicalize_url(raw.canonical_url.strip()) if raw.canonical_url else ""
    return NormalizedItem(
        id=raw.item_id,
        source_id=raw.source_id,
        domain=source_domain,
        run_id=run_id,
        title=title or content_text[:200],
        canonical_url=canonical_url,
        content_text=content_text,
        author=raw.author,
        published_at=published_at,
        fetched_at=fetched_at,
        dedup_hash=raw.dedup_hash,
        also_seen_in=None,
        metadata_json=raw.metadata,
    )


def build_source_occurrence(source_id: str, url: str | None, seen_at: datetime) -> dict[str, str | None]:
    return {
        "source_id": source_id,
        "url": canonicalize_url(url) if url else None,
        "seen_at": _ensure_utc(seen_at).isoformat(),
    }


def append_source_occurrence(
    also_seen_in: list[dict[str, Any]] | None,
    *,
    source_id: str,
    url: str | None,
    seen_at: datetime,
) -> list[dict[str, Any]]:
    occurrence = build_source_occurrence(source_id, url, seen_at)
    occurrences = list(also_seen_in or [])
    for existing in occurrences:
        if existing.get("source_id") == occurrence["source_id"] and existing.get("url") == occurrence["url"]:
            return occurrences
    occurrences.append(occurrence)
    return occurrences


def recompute_confidence_after_dedup(
    *,
    analysis_stage: int,
    current_confidence: str | None,
    source_authority: str,
    also_seen_in: list[dict[str, Any]] | None,
) -> str | None:
    if analysis_stage < 2:
        return current_confidence
    return derive_confidence(source_authority, also_seen_in)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
