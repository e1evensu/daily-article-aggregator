from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from src.collector.base import BaseCollector, RawItem
from src.config import settings

log = logging.getLogger(__name__)


def _parse_date(entry: dict, field: str) -> datetime | None:
    """Parse one RSS/Atom date field into UTC using several feedparser fallbacks."""
    raw = entry.get(field)
    if not raw:
        raw = entry.get("updated")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    parsed_struct = entry.get(f"{field}_parsed")
    if parsed_struct:
        try:
            from time import mktime
            return datetime.fromtimestamp(mktime(parsed_struct), tz=timezone.utc)
        except Exception:
            pass
    log.warning("Cannot parse date %r for entry %s", raw, entry.get("id", "?"))
    return None


def _extract_content(entry: dict, config: dict) -> str | None:
    """Extract the preferred content field from an RSS/Atom entry."""
    content_field = config.get("content_field", "summary")
    if content_field == "content":
        content_list = entry.get("content", [])
        if content_list and isinstance(content_list, list):
            return content_list[0].get("value")
    val = entry.get(content_field)
    if val:
        return val
    if entry.get("summary"):
        return entry["summary"]
    return None


def _extract_author(entry: dict, config: dict) -> str | None:
    """Extract the preferred author field from an RSS/Atom entry."""
    field = config.get("author_field", "author")
    if not field:
        return None
    val = entry.get(field)
    if val and val != "?":
        return val
    val = entry.get("dc_creator")
    if val:
        return val
    authors = entry.get("authors", [])
    if authors:
        return ", ".join(a.get("name", "") for a in authors if a.get("name"))
    return None


def _extract_native_id(entry: dict, config: dict) -> str | None:
    """Extract a stable native id from an RSS/Atom entry."""
    entry_id = entry.get("id")
    if not entry_id:
        return None
    native_id_mode = config.get("native_id_mode")
    if native_id_mode == "arxiv":
        return entry_id.split(":")[-1].split("v")[0]
    if native_id_mode == "path_basename":
        return entry_id.rstrip("/").split("/")[-1]
    return entry_id


class RSSCollector(BaseCollector):
    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        """Fetch an RSS/Atom feed and convert entries into RawItem records."""
        timeout = httpx.Timeout(float(self.config.get("timeout_s", settings.collector_timeout_s)))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        if feed.bozo and not feed.entries:
            raise ValueError(f"Feed parse error: {feed.bozo_exception}")

        date_field = self.config.get("date_field", "published")
        items = []

        for entry in feed.entries:
            pub_date = _parse_date(entry, date_field)

            if since and pub_date and pub_date < since:
                continue

            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title and not link:
                continue

            content = _extract_content(entry, self.config)
            author = _extract_author(entry, self.config)
            native_id = _extract_native_id(entry, self.config)

            items.append(RawItem(
                source_id=self.source_id,
                title=title,
                canonical_url=link,
                content_text=content,
                author=author,
                published_at=pub_date,
                native_id=native_id,
                metadata={"tags": [t.get("term") for t in entry.get("tags", []) if t.get("term")]},
            ))

        log.info("[%s] Fetched %d entries (%d after date filter)", self.source_id, len(feed.entries), len(items))
        return items
