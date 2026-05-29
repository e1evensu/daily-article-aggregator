from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.contracts import (
    decode_score_cursor,
    encode_score_cursor,
    raise_api_error,
    request_id,
    success_envelope,
)
from src.api.deps import require_api_token
from src.config import settings


class FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.state = SimpleNamespace()


def test_success_envelope_uses_existing_request_id_and_meta_fields():
    request = FakeRequest({"x-request-id": "req-1"})

    envelope = success_envelope([{"id": "item-1"}], request=request, next_cursor="cursor-1", total=1)

    assert envelope == {
        "data": [{"id": "item-1"}],
        "meta": {"request_id": "req-1", "next_cursor": "cursor-1", "total": 1},
    }
    assert request_id(request) == "req-1"


def test_score_cursor_round_trip_and_invalid_cursor_error():
    cursor = encode_score_cursor(92, "security_nvd_cve:CVE-2026-31415")

    decoded = decode_score_cursor(cursor)

    assert decoded.insight_score == 92
    assert decoded.item_id == "security_nvd_cve:CVE-2026-31415"

    with pytest.raises(HTTPException) as exc:
        decode_score_cursor("not-valid")
    assert exc.value.status_code == 400
    assert exc.value.detail == {"code": "invalid_cursor", "message": "Invalid cursor"}


def test_raise_api_error_uses_spec_error_shape():
    with pytest.raises(HTTPException) as exc:
        raise_api_error("not_found", "Item not found", 404)

    assert exc.value.status_code == 404
    assert exc.value.detail == {"code": "not_found", "message": "Item not found"}


@pytest.mark.asyncio
async def test_require_api_token_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "")

    assert await require_api_token(None) is None


@pytest.mark.asyncio
async def test_require_api_token_accepts_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "secret")

    assert await require_api_token("Bearer secret") is None


@pytest.mark.asyncio
async def test_require_api_token_rejects_missing_or_invalid_token(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "secret")

    with pytest.raises(HTTPException) as exc:
        await require_api_token(None)

    assert exc.value.status_code == 401
    assert exc.value.detail == {"code": "unauthorized", "message": "Invalid API token"}
