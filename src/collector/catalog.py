from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.source import Source


@dataclass(frozen=True)
class SourceCatalogEntry:
    id: str
    name: str
    domain: str
    type: str
    url: str
    authority: str
    fetch_strategy: str
    auth_mode: str = "none"
    status: str = "candidate"
    health: str = "good"
    is_active: bool = True
    config_json: dict[str, Any] = field(default_factory=dict)


def load_source_catalog(path: str | Path | None = None) -> tuple[SourceCatalogEntry, ...]:
    configured_path = path or settings.source_seed_path
    if not configured_path:
        return ()
    catalog_path = Path(configured_path)
    if not catalog_path.exists():
        return ()

    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("source catalog must be a JSON array")

    return tuple(_entry_from_dict(record) for record in raw)


def catalog_by_id(path: str | Path | None = None) -> dict[str, SourceCatalogEntry]:
    return {entry.id: entry for entry in load_source_catalog(path)}


def catalog_source_ids(path: str | Path | None = None) -> set[str]:
    return set(catalog_by_id(path))


def catalog_approved_source_ids(path: str | Path | None = None) -> set[str]:
    return {entry.id for entry in load_source_catalog(path) if entry.status == "approved"}


def as_source_model(entry: SourceCatalogEntry) -> Source:
    return Source(
        id=entry.id,
        name=entry.name,
        domain=entry.domain,
        type=entry.type,
        url=entry.url,
        auth_mode=entry.auth_mode,
        fetch_strategy=entry.fetch_strategy,
        authority=entry.authority,
        status=entry.status,
        health=entry.health,
        consecutive_failures=0,
        config_json=entry.config_json or None,
        is_active=entry.is_active,
    )


async def seed_candidate_sources(session: AsyncSession, path: str | Path | None = None) -> int:
    count = 0
    for entry in load_source_catalog(path):
        existing = await session.get(Source, entry.id)
        if existing is None:
            session.add(as_source_model(entry))
        else:
            _apply_catalog_entry(existing, entry)
        count += 1
    return count


def _apply_catalog_entry(source: Source, entry: SourceCatalogEntry) -> None:
    """Copy mutable catalog fields onto an existing source row."""
    source.name = entry.name
    source.domain = entry.domain
    source.type = entry.type
    source.url = entry.url
    source.auth_mode = entry.auth_mode
    source.fetch_strategy = entry.fetch_strategy
    source.authority = entry.authority
    source.status = entry.status
    source.config_json = entry.config_json or None
    source.is_active = entry.is_active


def _entry_from_dict(record: Any) -> SourceCatalogEntry:
    """Validate one raw JSON catalog record and convert it into a typed entry."""
    if not isinstance(record, dict):
        raise ValueError("source catalog entries must be objects")
    return SourceCatalogEntry(
        id=_required_str(record, "id"),
        name=_required_str(record, "name"),
        domain=_required_str(record, "domain"),
        type=_required_str(record, "type"),
        url=_required_str(record, "url"),
        authority=_required_str(record, "authority"),
        fetch_strategy=_required_str(record, "fetch_strategy"),
        auth_mode=str(record.get("auth_mode") or "none"),
        status=str(record.get("status") or "candidate"),
        health=str(record.get("health") or "good"),
        is_active=bool(record.get("is_active", True)),
        config_json=dict(record.get("config_json") or {}),
    )


def _required_str(record: dict[str, Any], key: str) -> str:
    """Require one non-empty string field in a source catalog record."""
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"source catalog entry requires non-empty {key}")
    return value.strip()
