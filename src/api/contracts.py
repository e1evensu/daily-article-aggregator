from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import ColumnElement

from src.collector.catalog import catalog_source_ids
from src.config import parse_csv, settings
from src.models.item import Item
from src.models.source import Source


@dataclass(frozen=True)
class ScoreCursor:
    insight_score: int
    item_id: str


def request_id(request: Request | None = None) -> str:
    """Get or assign the request id for the current request context."""
    if request is None:
        return uuid.uuid4().hex
    current = getattr(request.state, "request_id", None)
    if current:
        return current
    current = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = current
    return current


def success_envelope(
    data: Any,
    *,
    request: Request | None = None,
    next_cursor: str | None = None,
    total: int | None = None,
) -> dict[str, Any]:
    """Wrap successful data in the project's standard response envelope."""
    meta: dict[str, Any] = {"request_id": request_id(request), "next_cursor": next_cursor}
    if total is not None:
        meta["total"] = total
    return {"data": data, "meta": meta}


def error_envelope(
    code: str,
    message: str,
    *,
    request: Request | None = None,
) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}, "meta": {"request_id": request_id(request)}}


def raise_api_error(code: str, message: str, status_code: int) -> None:
    """Raise an HTTPException that follows the project's error contract."""
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


def allowed_domains() -> list[str]:
    return parse_csv(settings.digest_domains)


def allowed_source_ids() -> list[str]:
    return catalog_source_ids()


def visible_item_filters() -> tuple[ColumnElement[bool], ...]:
    """Keep the Phase 1 catalog/domain allowlist in one place for every item query."""
    return (
        Item.domain.in_(allowed_domains()),
        Item.source_id.in_(allowed_source_ids()),
    )


def visible_source_filters(*, only_active: bool = False) -> tuple[ColumnElement[bool], ...]:
    """Apply the shared source visibility rules and optionally exclude inactive records."""
    filters: list[ColumnElement[bool]] = [
        Source.domain.in_(allowed_domains()),
        Source.id.in_(allowed_source_ids()),
    ]
    if only_active:
        filters.append(Source.is_active.is_(True))
    return tuple(filters)


def encode_score_cursor(insight_score: int | None, item_id: str) -> str:
    payload = {"score": insight_score if insight_score is not None else -1, "id": item_id}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_score_cursor(cursor: str) -> ScoreCursor:
    """Decode and validate a score/id pagination cursor token."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        score = int(payload["score"])
        item_id = str(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise_api_error("invalid_cursor", "Invalid cursor", 400)
        raise AssertionError("unreachable") from exc
    return ScoreCursor(insight_score=score, item_id=item_id)
