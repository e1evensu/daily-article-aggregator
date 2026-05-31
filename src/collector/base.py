from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from abc import ABC, abstractmethod
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse


@dataclass
class RawItem:
    source_id: str
    title: str
    canonical_url: str
    content_text: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    native_id: str | None = None
    metadata: dict | None = None

    @property
    def dedup_hash(self) -> str:
        """Return the stable hash used to deduplicate items across collectors."""
        if self.canonical_url:
            normalized = canonicalize_url(self.canonical_url)
            return hashlib.sha256(normalized.encode()).hexdigest()[:32]
        text = normalize_text(self.title)
        if self.content_text:
            text += "|" + normalize_text(self.content_text)[:500]
        else:
            text += "|" + self.source_id
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    @property
    def item_id(self) -> str:
        """Return the bounded item id persisted in MySQL for this raw item."""
        if self.native_id:
            candidate = f"{self.source_id}:{self.native_id}"
            if len(candidate) <= 96:  # items.id is varchar(96)
                return candidate
            # native_id too long (e.g. an RSS <guid> URL) — hash it so item_id
            # stays within the column; deterministic, so dedup stays stable.
            suffix = hashlib.sha256(self.native_id.encode()).hexdigest()[:24]
            return f"{self.source_id}:{suffix}"
        return f"{self.source_id}:{self.dedup_hash[:16]}"


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref", "source", "fbclid", "gclid"}


def canonicalize_url(url: str) -> str:
    """Normalize a URL and strip tracking parameters before deduplication."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in qs.items() if k.lower() not in TRACKING_PARAMS}
    clean_query = urlencode(sorted(filtered.items()), doseq=True)
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/") or "/",
        parsed.params,
        clean_query,
        "",
    ))


def normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace for stable text-based hashing."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


class BaseCollector(ABC):
    def __init__(self, source_id: str, url: str, config: dict | None = None):
        self.source_id = source_id
        self.url = url
        self.config = config or {}

    @abstractmethod
    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        """Fetch raw items from the backing source, optionally bounded by time."""
        ...
