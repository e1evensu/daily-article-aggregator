from __future__ import annotations

from datetime import datetime, timezone

import httpx

from src.collector.base import BaseCollector, RawItem
from src.config import settings


class GitHubAdvisoryCollector(BaseCollector):
    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        """Fetch GitHub security advisories and project them into RawItem records."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = self.config.get("github_token") or settings.github_token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        params = {"per_page": self.config.get("per_page", settings.collector_github_per_page)}
        if since:
            params["published"] = f">={since.date().isoformat()}"

        timeout = httpx.Timeout(float(self.config.get("timeout_s", settings.collector_timeout_s)))
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
            transport=self.config.get("_transport"),
        ) as client:
            resp = await client.get(self.url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, list):
            raise ValueError("GitHub advisories response must be a list")

        items = []
        for advisory in data:
            published_at = _parse_datetime(advisory.get("published_at"))
            if since and published_at and published_at < since:
                continue

            ghsa_id = advisory.get("ghsa_id") or advisory.get("id")
            summary = advisory.get("summary") or ghsa_id or "GitHub security advisory"
            html_url = advisory.get("html_url") or advisory.get("url") or ""
            identifiers = advisory.get("identifiers") or []
            cve_ids = [i.get("value") for i in identifiers if i.get("type") == "CVE" and i.get("value")]

            items.append(
                RawItem(
                    source_id=self.source_id,
                    title=f"{ghsa_id}: {summary}" if ghsa_id and not summary.startswith(str(ghsa_id)) else summary,
                    canonical_url=html_url,
                    content_text=advisory.get("description"),
                    author="GitHub",
                    published_at=published_at,
                    native_id=ghsa_id,
                    metadata={
                        "severity": advisory.get("severity"),
                        "github_reviewed": advisory.get("github_reviewed"),
                        "cve_ids": cve_ids,
                        "updated_at": advisory.get("updated_at"),
                        "withdrawn_at": advisory.get("withdrawn_at"),
                        "vulnerabilities": advisory.get("vulnerabilities") or [],
                    },
                )
            )

        return items


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
