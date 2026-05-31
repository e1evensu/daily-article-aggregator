import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from src.collector.api import GenericAPICollector, HackerNewsCollector
from src.collector.dispatcher import collect_sources, collection_stats, create_collector, fetch_source
from src.collector.github import GitHubAdvisoryCollector
from src.collector.rss import RSSCollector


@pytest.mark.asyncio
async def test_github_advisory_collector_parses_advisories_with_cve_metadata():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/advisories"
        return httpx.Response(
            200,
            json=[
                {
                    "ghsa_id": "GHSA-7q4f-pgqx-h3vh",
                    "summary": "Example package vulnerability",
                    "description": "Detailed advisory text",
                    "html_url": "https://github.com/advisories/GHSA-7q4f-pgqx-h3vh",
                    "published_at": "2026-05-26T05:14:00Z",
                    "severity": "high",
                    "github_reviewed": True,
                    "identifiers": [{"type": "CVE", "value": "CVE-2026-31415"}],
                    "vulnerabilities": [{"package": {"name": "pkg"}}],
                }
            ],
        )

    collector = GitHubAdvisoryCollector(
        "security_github_advisories",
        "https://api.github.com/advisories",
        {"_transport": httpx.MockTransport(handler)},
    )

    items = await collector.fetch(since=datetime(2026, 5, 25, tzinfo=timezone.utc))

    assert len(items) == 1
    assert items[0].source_id == "security_github_advisories"
    assert items[0].native_id == "GHSA-7q4f-pgqx-h3vh"
    assert items[0].metadata["cve_ids"] == ["CVE-2026-31415"]
    assert items[0].metadata["severity"] == "high"


@pytest.mark.asyncio
async def test_generic_api_collector_accepts_items_envelope():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["since"] == "2026-05-26T00:00:00+00:00"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "a1",
                        "title": "Internal feed item",
                        "url": "https://example.com/item",
                        "content": "body",
                        "published_at": "2026-05-26T01:00:00Z",
                    }
                ]
            },
        )

    collector = GenericAPICollector(
        "security_sechub",
        "http://127.0.0.1:18210/api/feed",
        {"_transport": httpx.MockTransport(handler)},
    )

    items = await collector.fetch(since=datetime(2026, 5, 26, tzinfo=timezone.utc))

    assert len(items) == 1
    assert items[0].native_id == "a1"
    assert items[0].title == "Internal feed item"
    assert items[0].published_at == datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_hackernews_collector_filters_by_keywords():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v0/topstories.json":
            return httpx.Response(200, json=[1, 2])
        if request.url.path == "/v0/item/1.json":
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "type": "story",
                    "title": "New LLM agent runtime",
                    "url": "https://example.com/llm",
                    "by": "alice",
                    "time": 1779782400,
                    "score": 120,
                },
            )
        return httpx.Response(
            200,
            json={
                "id": 2,
                "type": "story",
                "title": "Gardening notes",
                "url": "https://example.com/garden",
                "by": "bob",
                "time": 1779782400,
                "score": 5,
            },
        )

    collector = HackerNewsCollector(
        "ai_hackernews",
        "https://hacker-news.firebaseio.com/v0/topstories.json",
        {"keyword_filter": ["llm", "security"], "max_items": 10, "_transport": httpx.MockTransport(handler)},
    )

    items = await collector.fetch()

    assert [item.native_id for item in items] == ["1"]
    assert items[0].metadata["hn_url"] == "https://news.ycombinator.com/item?id=1"


@pytest.mark.asyncio
async def test_hackernews_collector_fetches_story_items_concurrently():
    active = 0
    peak_active = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak_active
        if request.url.path == "/v0/topstories.json":
            return httpx.Response(200, json=[1, 2, 3, 4])

        active += 1
        peak_active = max(peak_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        story_id = request.url.path.rsplit("/", 1)[-1].split(".")[0]
        return httpx.Response(
            200,
            json={
                "id": int(story_id),
                "type": "story",
                "title": f"LLM security story {story_id}",
                "url": f"https://example.com/{story_id}",
                "by": "alice",
                "time": 1779782400,
                "score": 120,
            },
        )

    collector = HackerNewsCollector(
        "ai_hackernews",
        "https://hacker-news.firebaseio.com/v0/topstories.json",
        {
            "keyword_filter": ["llm", "security"],
            "max_items": 4,
            "max_concurrency": 4,
            "_transport": httpx.MockTransport(handler),
        },
    )

    started = time.monotonic()
    items = await collector.fetch()

    assert len(items) == 4
    assert peak_active > 1
    assert time.monotonic() - started < 0.15


def test_create_collector_uses_strategy_and_configured_collector_adapter():
    rss_source = SimpleNamespace(
        id="custom_rss_source",
        url="https://portswigger.net/research/rss",
        fetch_strategy="l1_rss",
        config_json={},
    )
    github_source = SimpleNamespace(
        id="custom_github_source",
        url="https://api.github.com/advisories",
        fetch_strategy="l1_github",
        config_json={},
    )
    hn_source = SimpleNamespace(
        id="custom_hn_source",
        url="https://hacker-news.firebaseio.com/v0/topstories.json",
        fetch_strategy="l1_api",
        config_json={"collector": "hackernews"},
    )

    assert isinstance(create_collector(rss_source), RSSCollector)
    assert isinstance(create_collector(github_source), GitHubAdvisoryCollector)
    assert isinstance(create_collector(hn_source), HackerNewsCollector)


@pytest.mark.asyncio
async def test_collect_sources_fetches_only_approved_active_sources_and_records_stats():
    approved = SimpleNamespace(
        id="security_nvd_cve",
        status="approved",
        health="good",
        is_active=True,
        consecutive_failures=2,
        last_fetch_at=None,
        last_fetch_status=None,
    )
    candidate = SimpleNamespace(
        id="ai_arxiv",
        status="candidate",
        health="good",
        is_active=True,
        consecutive_failures=0,
        last_fetch_at=None,
        last_fetch_status=None,
    )

    class FakeCollector:
        async def fetch(self, since=None):
            return []

    results = await collect_sources([approved, candidate], collector_factory=lambda source: FakeCollector())

    assert len(results) == 1
    assert results[0].source_id == "security_nvd_cve"
    assert approved.health == "good"
    assert approved.consecutive_failures == 0
    assert approved.last_fetch_status == "succeeded"
    assert candidate.last_fetch_status is None
    assert collection_stats(results)["security_nvd_cve"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_fetch_source_failure_degrades_then_disables_source():
    source = SimpleNamespace(
        id="security_portswigger",
        status="approved",
        health="good",
        is_active=True,
        consecutive_failures=2,
        last_fetch_at=None,
        last_fetch_status=None,
    )

    class FailingCollector:
        async def fetch(self, since=None):
            raise ValueError("bad feed")

    result = await fetch_source(source, collector_factory=lambda source: FailingCollector())

    assert result.status == "failed"
    assert result.error == "source_parse_error"
    assert source.consecutive_failures == 3
    assert source.health == "disabled"
    assert source.last_fetch_status == "source_parse_error"
