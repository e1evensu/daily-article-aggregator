from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import httpx

from src.collector.base import BaseCollector, RawItem
from src.config import settings

log = logging.getLogger(__name__)


class NVDCollector(BaseCollector):
    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        """Fetch recent NVD CVEs and project them into RawItem records."""
        if not since:
            since = datetime.now(timezone.utc) - timedelta(
                hours=int(self.config.get("default_since_hours", settings.collector_default_since_hours))
            )

        params = {
            "pubStartDate": since.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "pubEndDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.999"),
            "resultsPerPage": int(self.config.get("results_per_page", settings.collector_nvd_results_per_page)),
        }
        headers = {}
        nvd_key = self.config.get("nvd_api_key", "")
        if nvd_key:
            headers["apiKey"] = nvd_key

        timeout = httpx.Timeout(float(self.config.get("timeout_s", settings.collector_timeout_s)))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = await client.get(self.url, params=params)
            resp.raise_for_status()
            data = resp.json()

        total = data.get("totalResults", 0)
        vulns = data.get("vulnerabilities", [])
        log.info("[%s] NVD returned %d/%d CVEs", self.source_id, len(vulns), total)

        items = []
        for v in vulns:
            cve = v.get("cve", {})
            cve_id = cve.get("id", "")
            descriptions = cve.get("descriptions", [])
            en_desc = next((d["value"] for d in descriptions if d.get("lang") == "en"), "")
            zh_desc = next((d["value"] for d in descriptions if d.get("lang") == "zh"), None)

            published = cve.get("published")
            pub_dt = None
            if published:
                try:
                    pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(timezone.utc)
                except Exception:
                    pass

            refs = cve.get("references", [])
            ref_urls = [r.get("url") for r in refs if r.get("url")]
            canonical = f"https://nvd.nist.gov/vuln/detail/{cve_id}"

            metrics = cve.get("metrics", {})
            cvss_score = None
            cvss_vector = None
            for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                metric_list = metrics.get(key, [])
                if metric_list:
                    cvss_data = metric_list[0].get("cvssData", {})
                    cvss_score = cvss_data.get("baseScore")
                    cvss_vector = cvss_data.get("vectorString")
                    break

            weaknesses = cve.get("weaknesses", [])
            cwe_ids = []
            for w in weaknesses:
                for d in w.get("description", []):
                    if d.get("value", "").startswith("CWE-"):
                        cwe_ids.append(d["value"])

            items.append(RawItem(
                source_id=self.source_id,
                title=f"{cve_id}: {en_desc[:200]}" if en_desc else cve_id,
                canonical_url=canonical,
                content_text=en_desc,
                published_at=pub_dt,
                native_id=cve_id,
                metadata={
                    "cve_id": cve_id,
                    "cvss_score": cvss_score,
                    "cvss_vector": cvss_vector,
                    "cwe_ids": cwe_ids,
                    "references": ref_urls[:10],
                    "zh_description": zh_desc,
                    "vuln_status": cve.get("vulnStatus"),
                },
            ))

        return items
