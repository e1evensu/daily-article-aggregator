from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.contracts import (
    decode_score_cursor,
    encode_score_cursor,
    error_envelope,
    raise_api_error,
    request_id,
    success_envelope,
)
from src.api.deps import require_api_token
from src.api.digests import get_digest, latest_digest
from src.api.items import get_item
from src.api.digests import Digest, select as digest_select
from src.api.items import Item, select as item_select
from src.api.runs import get_run, latest_run
from src.api.sources import get_source
from src.api.sources import Source, select as source_select
from src.api.stats import select as stats_select
from src.api.sources import router as sources_router
from src.config import settings


class FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.state = SimpleNamespace()


class FakeScalarResult:
    def scalar_one_or_none(self):
        """Mimic SQLAlchemy's scalar_one_or_none with an always-empty result."""
        return None


class CapturingSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        """Record executed statements and return an empty scalar result."""
        self.statements.append(statement)
        return FakeScalarResult()

    async def get(self, *_args, **_kwargs):
        return None


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


def test_error_envelope_attaches_request_id():
    request = FakeRequest({"x-request-id": "req-2"})

    envelope = error_envelope("not_found", "Digest not found", request=request)

    assert envelope == {
        "error": {"code": "not_found", "message": "Digest not found"},
        "meta": {"request_id": "req-2"},
    }


def test_sources_router_is_read_only_for_phase1_contract():
    routes = {(route.path, ",".join(sorted(route.methods))) for route in sources_router.routes}

    assert ("/sources", "GET") in routes
    assert ("/sources/{source_id}", "GET") in routes
    assert not any("PUT" in methods or "PATCH" in methods or "POST" in methods for _, methods in routes)


def test_api_queries_can_be_limited_to_phase1_domains_and_catalog_sources():
    item_stmt = item_select(Item).where(Item.domain.in_(["security", "ai"]), Item.source_id.in_(["security_nvd_cve"]))
    source_stmt = source_select(Source).where(Source.domain.in_(["security", "ai"]), Source.id.in_(["security_nvd_cve"]))
    stats_stmt = stats_select(Source).where(Source.domain.in_(["security", "ai"]), Source.id.in_(["security_nvd_cve"]))
    digest_stmt = digest_select(Digest).where(Digest.domain.in_(["security", "ai"]))

    assert "items.domain IN" in str(item_stmt)
    assert "items.source_id IN" in str(item_stmt)
    assert "sources.domain IN" in str(source_stmt)
    assert "sources.id IN" in str(source_stmt)
    assert "sources.domain IN" in str(stats_stmt)
    assert "sources.id IN" in str(stats_stmt)
    assert "digests.domain IN" in str(digest_stmt)


@pytest.mark.asyncio
async def test_item_detail_query_is_limited_to_phase1_domains_and_catalog_sources():
    session = CapturingSession()

    with pytest.raises(HTTPException):
        await get_item("legacy-item", FakeRequest(), session)

    sql = str(session.statements[0])
    assert "items.id = :id_1" in sql
    assert "items.domain IN" in sql
    assert "items.source_id IN" in sql


@pytest.mark.asyncio
async def test_source_detail_query_is_limited_to_phase1_domains_and_catalog_sources():
    session = CapturingSession()

    with pytest.raises(HTTPException) as exc:
        await get_source("legacy-source", FakeRequest(), session)

    sql = str(session.statements[0])
    assert "sources.id = :id_1" in sql
    assert "sources.domain IN" in sql
    assert "sources.id IN" in sql
    assert exc.value.status_code == 404
    assert exc.value.detail == {"code": "not_found", "message": "Source not found"}


@pytest.mark.asyncio
async def test_digest_detail_invalid_domain_is_not_found():
    with pytest.raises(HTTPException) as exc:
        await get_digest("2026-05-31", FakeRequest(), domain="general", db=CapturingSession())

    assert exc.value.status_code == 404
    assert exc.value.detail == {"code": "not_found", "message": "Digest not found"}


@pytest.mark.asyncio
async def test_latest_digest_without_data_raises_not_found():
    with pytest.raises(HTTPException) as exc:
        await latest_digest(FakeRequest(), db=CapturingSession())

    assert exc.value.status_code == 404
    assert exc.value.detail == {"code": "not_found", "message": "No digest found"}


@pytest.mark.asyncio
async def test_latest_run_without_data_raises_not_found():
    with pytest.raises(HTTPException) as exc:
        await latest_run(FakeRequest(), db=CapturingSession())

    assert exc.value.status_code == 404
    assert exc.value.detail == {"code": "not_found", "message": "No runs found"}


@pytest.mark.asyncio
async def test_run_detail_without_data_raises_not_found():
    with pytest.raises(HTTPException) as exc:
        await get_run("run_1", FakeRequest(), db=CapturingSession())

    assert exc.value.status_code == 404
    assert exc.value.detail == {"code": "not_found", "message": "Run not found"}


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
