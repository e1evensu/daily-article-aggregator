from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from src.api.contracts import encode_score_cursor
from src.api.items import _parse_iso_datetime, _serialize_item


class FakeItem:
    def __init__(self):
        self.id = "security_nvd_cve:CVE-2026-31415"
        self.source_id = "security_nvd_cve"
        self.domain = "security"
        self.title = "CVE-2026-31415"
        self.canonical_url = "https://nvd.nist.gov/vuln/detail/CVE-2026-31415"
        self.author = "NVD"
        self.published_at = datetime(2026, 5, 26, 5, 14, tzinfo=timezone.utc)
        self.fetched_at = datetime(2026, 5, 26, 7, 36, tzinfo=timezone.utc)
        self.also_seen_in = [{"source_id": "security_github_advisories", "url": "https://example.com", "seen_at": "..."}]
        self.category = "vulnerability"
        self.tags = ["cve", "linux"]
        self.summary_zh = "摘要"
        self.insight_score = 92
        self.credibility = "high"
        self.confidence = "confirmed"
        self.trend_signal = "emerging"
        self.recommendation_reason = "reason"
        self.action_suggestion = "action"
        self.analysis_stage = 2
        self.stage1_model = "deepseek-ai/deepseek-v4-flash"
        self.stage1_provider = "nvidia"
        self.stage1_prompt_version = "s1_v1"
        self.stage1_analyzed_at = datetime(2026, 5, 26, 7, 39, tzinfo=timezone.utc)
        self.stage2_model = "deepseek-ai/deepseek-v4-pro"
        self.stage2_provider = "nvidia"
        self.stage2_prompt_version = "s2_v1"
        self.stage2_analyzed_at = datetime(2026, 5, 26, 7, 43, tzinfo=timezone.utc)
        self.expires_at = None


def test_serialize_item_matches_api_field_names():
    data = _serialize_item(FakeItem())

    assert data["id"] == "security_nvd_cve:CVE-2026-31415"
    assert data["source_id"] == "security_nvd_cve"
    assert data["stage1_model"] == "deepseek-ai/deepseek-v4-flash"
    assert data["stage2_prompt_version"] == "s2_v1"
    assert data["also_seen_in"] == [
        {"source_id": "security_github_advisories", "url": "https://example.com", "seen_at": "..."}
    ]
    assert "analysis_model" not in data
    assert "prompt_version" not in data


def test_parse_iso_datetime_accepts_zulu_and_rejects_bad_values():
    parsed = _parse_iso_datetime("2026-05-26T05:14:00Z", "since")

    assert parsed == datetime(2026, 5, 26, 5, 14, tzinfo=timezone.utc)

    with pytest.raises(HTTPException) as exc:
        _parse_iso_datetime("not-a-date", "since")

    assert exc.value.status_code == 400
    assert exc.value.detail == {"code": "invalid_param", "message": "since must be an ISO timestamp"}


def test_item_cursor_encoding_is_opaque_but_decodable_by_contract():
    cursor = encode_score_cursor(92, "security_nvd_cve:CVE-2026-31415")

    assert "security_nvd_cve" not in cursor
    assert ":" not in cursor
