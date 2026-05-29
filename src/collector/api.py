from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from src.collector.base import BaseCollector, RawItem
from src.config import settings


class GenericAPICollector(BaseCollector):
    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        params = {}
        if since:
            params["since"] = since.isoformat()

        timeout = httpx.Timeout(float(self.config.get("timeout_s", settings.collector_timeout_s)))
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            transport=self.config.get("_transport"),
        ) as client:
            resp = await client.get(self.url, params=params)
            resp.raise_for_status()
            data = resp.json()

        records = _extract_records(data)
        return [self._record_to_raw_item(record) for record in records]

    def _record_to_raw_item(self, record: dict[str, Any]) -> RawItem:
        title_field = self.config.get("title_field", "title")
        url_field = self.config.get("url_field", "url")
        content_field = self.config.get("content_field", "content")
        author_field = self.config.get("author_field", "author")
        published_field = self.config.get("published_at_field", "published_at")
        native_id_field = self.config.get("native_id_field", "id")

        return RawItem(
            source_id=self.source_id,
            title=str(record.get(title_field) or "").strip(),
            canonical_url=str(record.get(url_field) or record.get("canonical_url") or "").strip(),
            content_text=record.get(content_field) or record.get("summary") or record.get("description"),
            author=record.get(author_field),
            published_at=_parse_datetime(record.get(published_field)),
            native_id=str(record.get(native_id_field)) if record.get(native_id_field) is not None else None,
            metadata={k: v for k, v in record.items() if k not in {title_field, url_field, content_field}},
        )


class HackerNewsCollector(BaseCollector):
    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        timeout = httpx.Timeout(float(self.config.get("timeout_s", settings.collector_timeout_s)))
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            transport=self.config.get("_transport"),
        ) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
            story_ids = resp.json()
            if not isinstance(story_ids, list):
                raise ValueError("Hacker News top stories response must be a list")

            items = []
            max_items = int(self.config.get("max_items", settings.collector_hn_max_items))
            for story_id in story_ids[:max_items]:
                item_resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
                item_resp.raise_for_status()
                story = item_resp.json()
                if not isinstance(story, dict) or story.get("type") != "story":
                    continue
                raw_item = self._story_to_raw_item(story)
                if since and raw_item.published_at and raw_item.published_at < since:
                    continue
                if not _matches_keywords(raw_item, self.config.get("keyword_filter") or []):
                    continue
                items.append(raw_item)

        return items

    def _story_to_raw_item(self, story: dict[str, Any]) -> RawItem:
        story_id = str(story.get("id"))
        url = story.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        return RawItem(
            source_id=self.source_id,
            title=str(story.get("title") or "").strip(),
            canonical_url=url,
            content_text=story.get("text"),
            author=story.get("by"),
            published_at=_parse_unix_timestamp(story.get("time")),
            native_id=story_id,
            metadata={
                "score": story.get("score"),
                "descendants": story.get("descendants"),
                "hn_url": f"https://news.ycombinator.com/item?id={story_id}",
            },
        )


def _extract_records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = data.get("items") or data.get("data") or data.get("results") or []
    else:
        raise ValueError("API response must be a list or object")

    if not isinstance(records, list):
        raise ValueError("API response records must be a list")
    return [record for record in records if isinstance(record, dict)]


def _matches_keywords(item: RawItem, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = " ".join([item.title or "", item.content_text or "", item.canonical_url or ""]).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_unix_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
