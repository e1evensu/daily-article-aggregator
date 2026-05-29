from datetime import datetime, timedelta, timezone

import pytest

from src.collector.base import RawItem
from src.pipeline.ingestion import (
    NormalizationError,
    append_source_occurrence,
    normalize_raw_item,
    recompute_confidence_after_dedup,
)


def test_normalize_raw_item_canonicalizes_url_and_sets_item_contract():
    now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
    raw = RawItem(
        source_id="security_nvd_cve",
        title=" CVE-2026-31415 ",
        canonical_url="HTTPS://Example.COM/path/?utm_source=x&b=2&a=1#frag",
        content_text=" details ",
        author="NVD",
        published_at=now,
        native_id="CVE-2026-31415",
        metadata={"cve_id": "CVE-2026-31415"},
    )

    item = normalize_raw_item(raw, source_domain="security", run_id="run_1", now=now)

    assert item.id == "security_nvd_cve:CVE-2026-31415"
    assert item.source_id == "security_nvd_cve"
    assert item.domain == "security"
    assert item.run_id == "run_1"
    assert item.title == "CVE-2026-31415"
    assert item.canonical_url == "https://example.com/path?a=1&b=2"
    assert item.content_text == "details"
    assert item.published_at == now
    assert item.fetched_at == now
    assert item.dedup_hash == raw.dedup_hash
    assert item.also_seen_in is None
    assert item.metadata_json == {"cve_id": "CVE-2026-31415"}


def test_normalize_raw_item_rejects_empty_item():
    raw = RawItem(source_id="ai_arxiv", title="", canonical_url="", content_text=None)

    with pytest.raises(NormalizationError):
        normalize_raw_item(raw, source_domain="ai")


def test_normalize_raw_item_rejects_timestamp_more_than_seven_days_in_future():
    now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
    raw = RawItem(
        source_id="ai_arxiv",
        title="future paper",
        canonical_url="https://example.com/paper",
        published_at=now + timedelta(days=8),
    )

    with pytest.raises(NormalizationError):
        normalize_raw_item(raw, source_domain="ai", now=now)


def test_append_source_occurrence_uses_spec_shape_and_deduplicates_same_source_url():
    seen_at = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)

    occurrences = append_source_occurrence(
        None,
        source_id="security_github_advisories",
        url="https://Example.com/advisory?utm_campaign=x",
        seen_at=seen_at,
    )
    occurrences = append_source_occurrence(
        occurrences,
        source_id="security_github_advisories",
        url="https://example.com/advisory",
        seen_at=seen_at + timedelta(minutes=5),
    )

    assert occurrences == [
        {
            "source_id": "security_github_advisories",
            "url": "https://example.com/advisory",
            "seen_at": "2026-05-26T08:00:00+00:00",
        }
    ]


def test_recompute_confidence_after_dedup_only_for_stage2_items():
    occurrences = [
        {"source_id": "security_project_zero", "url": "https://example.com/1"},
        {"source_id": "security_github_advisories", "url": "https://example.com/2"},
    ]

    assert (
        recompute_confidence_after_dedup(
            analysis_stage=1,
            current_confidence=None,
            source_authority="regular",
            also_seen_in=occurrences,
        )
        is None
    )
    assert (
        recompute_confidence_after_dedup(
            analysis_stage=2,
            current_confidence="tentative",
            source_authority="regular",
            also_seen_in=occurrences,
        )
        == "confirmed"
    )
