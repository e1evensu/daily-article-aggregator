from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.ai.analyzer import Stage1Outcome, Stage2Outcome
from src.ai.contracts import Stage1Analysis, Stage2Analysis
from src.pipeline.ingestion import NormalizedItem
from src.pipeline.persistence import (
    apply_stage1_outcome,
    apply_stage2_outcome,
    item_model_from_normalized,
    merge_duplicate_occurrence,
    persist_normalized_items,
    source_authority_map,
)


class FakeResult:
    def __init__(self, item):
        self.item = item

    def scalar_one_or_none(self):
        """Return the prepared item for fake scalar lookups."""
        return self.item


class FakeSession:
    def __init__(self, existing_by_hash=None, fail_on_execute=False):
        self.existing_by_hash = existing_by_hash or {}
        self.fail_on_execute = fail_on_execute
        self.added = []

    async def execute(self, stmt):
        """Return fake dedup lookups or raise a configured DB failure."""
        if self.fail_on_execute:
            raise RuntimeError("db failed")
        where = list(stmt._where_criteria)[0]
        dedup_hash = where.right.value
        return FakeResult(self.existing_by_hash.get(dedup_hash))

    def add(self, item):
        """Record inserted ORM items."""
        self.added.append(item)


def _normalized(**overrides):
    """Build a standard NormalizedItem payload for persistence tests."""
    values = {
        "id": "security_nvd_cve:CVE-1",
        "source_id": "security_nvd_cve",
        "domain": "security",
        "run_id": "run_1",
        "title": "CVE-1",
        "canonical_url": "https://nvd.nist.gov/vuln/detail/CVE-1",
        "content_text": "details",
        "author": "NVD",
        "published_at": datetime(2026, 5, 26, 5, 0, tzinfo=timezone.utc),
        "fetched_at": datetime(2026, 5, 26, 6, 0, tzinfo=timezone.utc),
        "dedup_hash": "hash-1",
        "also_seen_in": None,
        "metadata_json": {"cve_id": "CVE-1"},
    }
    values.update(overrides)
    return NormalizedItem(**values)


def test_item_model_from_normalized_sets_pending_analysis_defaults():
    model = item_model_from_normalized(_normalized())

    assert model.id == "security_nvd_cve:CVE-1"
    assert model.analysis_stage == 0
    assert model.credibility == "unknown"
    assert model.metadata_json == {"cve_id": "CVE-1"}


def test_merge_duplicate_occurrence_adds_cross_source_and_recomputes_stage2_confidence():
    existing = item_model_from_normalized(_normalized())
    existing.analysis_stage = 2
    existing.confidence = "firm"
    duplicate = _normalized(
        id="security_github_advisories:GHSA-1",
        source_id="security_github_advisories",
        canonical_url="https://github.com/advisories/GHSA-1?utm_source=x",
    )

    merge_duplicate_occurrence(
        existing,
        duplicate,
        {"security_nvd_cve": "official", "security_github_advisories": "official"},
    )

    assert existing.also_seen_in == [
        {
            "source_id": "security_github_advisories",
            "url": "https://github.com/advisories/GHSA-1",
            "seen_at": "2026-05-26T06:00:00+00:00",
        }
    ]
    assert existing.confidence == "confirmed"


def test_merge_duplicate_same_source_does_not_append_occurrence():
    existing = item_model_from_normalized(_normalized())
    duplicate = _normalized(canonical_url="https://nvd.nist.gov/vuln/detail/CVE-1")

    merge_duplicate_occurrence(existing, duplicate, {"security_nvd_cve": "official"})

    assert existing.also_seen_in is None


@pytest.mark.asyncio
async def test_persist_normalized_items_inserts_new_and_counts_duplicates():
    existing = item_model_from_normalized(_normalized(dedup_hash="hash-existing"))
    duplicate = _normalized(
        id="security_github_advisories:GHSA-1",
        source_id="security_github_advisories",
        dedup_hash="hash-existing",
        canonical_url="https://github.com/advisories/GHSA-1",
    )
    new_item = _normalized(id="security_nvd_cve:CVE-2", dedup_hash="hash-new")
    session = FakeSession(existing_by_hash={"hash-existing": existing})

    result = await persist_normalized_items(
        session,
        [duplicate, new_item],
        source_authority_by_id={"security_nvd_cve": "official", "security_github_advisories": "official"},
    )

    assert result.duplicates == 1
    assert result.errors == 0
    assert [item.id for item in result.inserted] == ["security_nvd_cve:CVE-2"]
    assert [item.id for item in session.added] == ["security_nvd_cve:CVE-2"]
    assert existing.also_seen_in[0]["source_id"] == "security_github_advisories"


@pytest.mark.asyncio
async def test_persist_normalized_items_counts_per_item_errors():
    session = FakeSession(fail_on_execute=True)

    result = await persist_normalized_items(
        session,
        [_normalized(), _normalized(id="security_nvd_cve:CVE-2", dedup_hash="hash-2")],
        source_authority_by_id={"security_nvd_cve": "official"},
    )

    assert result.inserted == []
    assert result.duplicates == 0
    assert result.errors == 2


def test_source_authority_map_uses_source_ids():
    sources = [
        SimpleNamespace(id="security_nvd_cve", authority="official"),
        SimpleNamespace(id="security_portswigger", authority="authoritative"),
    ]

    assert source_authority_map(sources) == {
        "security_nvd_cve": "official",
        "security_portswigger": "authoritative",
    }


def test_apply_stage1_outcome_sets_analysis_fields_and_retention():
    item = item_model_from_normalized(_normalized())
    analyzed_at = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
    outcome = Stage1Outcome(
        analysis=Stage1Analysis(
            category="vulnerability",
            tags=["cve", "linux"],
            summary_zh="摘要",
            insight_score=82,
            credibility="high",
        ),
        provider="nvidia",
        model="deepseek-ai/deepseek-v4-flash",
        prompt_version="s1_v1",
        analyzed_at=analyzed_at,
        expires_at=None,
        error=None,
    )

    apply_stage1_outcome(item, outcome)

    assert item.analysis_stage == 1
    assert item.category == "vulnerability"
    assert item.tags == ["cve", "linux"]
    assert item.summary_zh == "摘要"
    assert item.insight_score == 82
    assert item.credibility == "high"
    assert item.stage1_model == "deepseek-ai/deepseek-v4-flash"
    assert item.stage1_provider == "nvidia"
    assert item.stage1_prompt_version == "s1_v1"
    assert item.stage1_analyzed_at == analyzed_at
    assert item.stage1_error is None
    assert item.expires_at is None


def test_apply_stage1_failure_keeps_item_pending_with_error():
    item = item_model_from_normalized(_normalized())
    analyzed_at = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
    outcome = Stage1Outcome(
        analysis=None,
        provider=None,
        model="deepseek-ai/deepseek-v4-flash",
        prompt_version="s1_v1",
        analyzed_at=analyzed_at,
        expires_at=None,
        error="model_parse_error",
    )

    apply_stage1_outcome(item, outcome)

    assert item.analysis_stage == 0
    assert item.stage1_error == "model_parse_error"
    assert item.category is None
    assert item.insight_score is None


def test_apply_stage2_outcome_sets_recommendation_fields():
    item = item_model_from_normalized(_normalized())
    item.analysis_stage = 1
    analyzed_at = datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc)
    outcome = Stage2Outcome(
        analysis=Stage2Analysis(
            recommendation_reason="值得优先处理",
            confidence="confirmed",
            trend_signal="growing",
            action_suggestion="确认资产影响",
        ),
        provider="nvidia",
        model="deepseek-ai/deepseek-v4-pro",
        prompt_version="s2_v1",
        analyzed_at=analyzed_at,
        error=None,
    )

    apply_stage2_outcome(item, outcome)

    assert item.analysis_stage == 2
    assert item.recommendation_reason == "值得优先处理"
    assert item.confidence == "confirmed"
    assert item.trend_signal == "growing"
    assert item.action_suggestion == "确认资产影响"
    assert item.stage2_model == "deepseek-ai/deepseek-v4-pro"
    assert item.stage2_provider == "nvidia"
    assert item.stage2_prompt_version == "s2_v1"
    assert item.stage2_analyzed_at == analyzed_at
    assert item.stage2_error is None


def test_apply_stage2_failure_keeps_stage1_complete_and_sets_error():
    item = item_model_from_normalized(_normalized())
    item.analysis_stage = 1
    outcome = Stage2Outcome(
        analysis=None,
        provider=None,
        model="deepseek-ai/deepseek-v4-pro",
        prompt_version="s2_v1",
        analyzed_at=datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc),
        error="model_provider_error",
    )

    apply_stage2_outcome(item, outcome)

    assert item.analysis_stage == 1
    assert item.stage2_error == "model_provider_error"
    assert item.confidence is None
