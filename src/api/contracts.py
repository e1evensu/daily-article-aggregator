from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class ScoreCursor:
    insight_score: int
    item_id: str


def request_id(request: Request | None = None) -> str:
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
    meta: dict[str, Any] = {"request_id": request_id(request), "next_cursor": next_cursor}
    if total is not None:
        meta["total"] = total
    return {"data": data, "meta": meta}


def raise_api_error(code: str, message: str, status_code: int) -> None:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


def encode_score_cursor(insight_score: int | None, item_id: str) -> str:
    payload = {"score": insight_score if insight_score is not None else -1, "id": item_id}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_score_cursor(cursor: str) -> ScoreCursor:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        score = int(payload["score"])
        item_id = str(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise_api_error("invalid_cursor", "Invalid cursor", 400)
        raise AssertionError("unreachable") from exc
    return ScoreCursor(insight_score=score, item_id=item_id)
