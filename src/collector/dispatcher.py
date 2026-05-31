from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from src.collector.api import GenericAPICollector, HackerNewsCollector
from src.collector.base import BaseCollector, RawItem
from src.collector.github import GitHubAdvisoryCollector
from src.collector.nvd import NVDCollector
from src.collector.rss import RSSCollector
from src.config import settings


@dataclass(frozen=True)
class SourceFetchResult:
    source_id: str
    status: str
    items: list[RawItem] = field(default_factory=list)
    error: str | None = None
    duration_s: float = 0.0

    def stats_entry(self) -> dict[str, Any]:
        """Build the per-source stats fragment stored on the run record."""
        data: dict[str, Any] = {"status": self.status, "items": len(self.items), "duration_s": round(self.duration_s, 3)}
        if self.error:
            data["error"] = self.error
        return data


def create_collector(source: Any) -> BaseCollector:
    config = dict(getattr(source, "config_json", None) or {})
    source_id = source.id
    url = source.url
    collector_name = config.get("collector")

    if collector_name == "nvd" or getattr(source, "type", None) == "nvd_api":
        return NVDCollector(source_id, url, config)
    if collector_name == "github_advisories" or getattr(source, "fetch_strategy", None) == "l1_github":
        return GitHubAdvisoryCollector(source_id, url, config)
    if collector_name == "hackernews":
        return HackerNewsCollector(source_id, url, config)
    if getattr(source, "fetch_strategy", None) == "l1_rss":
        return RSSCollector(source_id, url, config)
    if getattr(source, "fetch_strategy", None) == "l1_api":
        return GenericAPICollector(source_id, url, config)

    raise ValueError(f"Unsupported collector for source {source_id}")


async def collect_sources(
    sources: list[Any],
    *,
    since: datetime | None = None,
    collector_factory=create_collector,
) -> list[SourceFetchResult]:
    """Fetch all eligible sources serially and return their normalized fetch results."""
    results = []
    for source in sources:
        if not _should_fetch(source):
            continue
        result = await fetch_source(source, since=since, collector_factory=collector_factory)
        results.append(result)
    return results


async def fetch_source(
    source: Any,
    *,
    since: datetime | None = None,
    collector_factory=create_collector,
) -> SourceFetchResult:
    """Fetch one source and normalize failures into a structured result."""
    started = time.monotonic()
    try:
        collector = collector_factory(source)
        items = await collector.fetch(since=since)
    except Exception as exc:
        duration = time.monotonic() - started
        error = classify_fetch_error(exc)
        _mark_source_failure(source, error)
        return SourceFetchResult(
            source_id=source.id,
            status="failed",
            error=error,
            duration_s=duration,
        )

    duration = time.monotonic() - started
    _mark_source_success(source)
    return SourceFetchResult(
        source_id=source.id,
        status="succeeded",
        items=items,
        duration_s=duration,
    )


def classify_fetch_error(exc: Exception) -> str:
    """Map collector exceptions into the stable source error categories."""
    if isinstance(exc, httpx.TimeoutException):
        return "source_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (401, 403):
            return "source_auth_error"
        return "source_http_error"
    if isinstance(exc, httpx.HTTPError):
        return "source_http_error"
    return "source_parse_error"


def collection_stats(results: list[SourceFetchResult]) -> dict[str, dict[str, Any]]:
    return {result.source_id: result.stats_entry() for result in results}


def _should_fetch(source: Any) -> bool:
    """Return whether a source is active, approved, and not disabled."""
    return (
        getattr(source, "is_active", False)
        and getattr(source, "status", None) == "approved"
        and getattr(source, "health", None) != "disabled"
    )


def _mark_source_success(source: Any) -> None:
    """Update source health fields after a successful fetch."""
    source.health = "good"
    source.consecutive_failures = 0
    source.last_fetch_at = datetime.now(timezone.utc)
    source.last_fetch_status = "succeeded"


def _mark_source_failure(source: Any, error: str) -> None:
    """Update source health fields after a failed fetch attempt."""
    failures = int(getattr(source, "consecutive_failures", 0) or 0) + 1
    source.consecutive_failures = failures
    source.health = "disabled" if failures >= settings.collector_failure_disable_threshold else "degraded"
    source.last_fetch_at = datetime.now(timezone.utc)
    source.last_fetch_status = error
