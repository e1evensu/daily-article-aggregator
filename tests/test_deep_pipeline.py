from datetime import datetime, timezone

import pytest

from src.config import settings
from src.deep import worker
from src.deep.pipeline import enqueue_candidates, enqueue_paper, extract_arxiv_id, extract_ghsa, select_candidates
from src.pipeline.ingestion import NormalizedItem
from src.pipeline.persistence import item_model_from_normalized


class FakeResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def first(self):
        """Return the first fake row, mirroring SQLAlchemy result helpers."""
        return self.rows[0] if self.rows else None

    def all(self):
        """Return all fake rows."""
        return self.rows

    @property
    def rowcount(self):
        return len(self.rows)


class FakeSession:
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.executed = []
        self.commits = 0

    async def execute(self, statement):
        """Capture executed statements and return fake existing-subject rows."""
        self.executed.append(statement)
        text = str(statement)
        if text.startswith("SELECT"):
            return FakeResult([(value,) for value in self.existing])
        return FakeResult()

    async def commit(self):
        """Record explicit commit attempts, which should stay at zero in these tests."""
        self.commits += 1


class WorkerSession:
    def __init__(self):
        self.executed = []
        self.commits = 0

    async def execute(self, statement):
        self.executed.append(str(statement))
        sql = str(statement)
        if "SELECT deep_analyses.id" in sql:
            return FakeResult([("GHSA-7q4f-pgqx-h3vh", "item-1", "vuln_rca")])
        if "UPDATE deep_analyses" in sql:
            return FakeResult([("updated",)])
        return FakeResult()

    async def commit(self):
        self.commits += 1


def _item(**overrides):
    """Build a normalized item model suitable for deep-pipeline candidate tests."""
    insight_score = overrides.pop("insight_score", 80)
    values = {
        "id": "security_github_advisories:GHSA-7q4f-pgqx-h3vh",
        "source_id": "security_github_advisories",
        "domain": "security",
        "run_id": "run_1",
        "title": "GHSA-7q4f-pgqx-h3vh example advisory",
        "canonical_url": "https://github.com/advisories/GHSA-7q4f-pgqx-h3vh",
        "content_text": "details",
        "author": None,
        "published_at": datetime(2026, 5, 26, 5, 0, tzinfo=timezone.utc),
        "fetched_at": datetime(2026, 5, 26, 6, 0, tzinfo=timezone.utc),
        "dedup_hash": "hash-1",
        "also_seen_in": None,
        "metadata_json": None,
    }
    values.update(overrides)
    model = item_model_from_normalized(NormalizedItem(**values))
    model.insight_score = insight_score
    return model


def test_extract_deep_subject_ids_from_items():
    assert extract_ghsa(_item()) == "GHSA-7q4f-pgqx-h3vh"
    assert extract_arxiv_id(_item(id="ai_arxiv:2512.07921", domain="ai", canonical_url="https://arxiv.org/abs/2512.07921")) == "2512.07921"


def test_select_candidates_filters_security_ghsa_items_by_score():
    high = _item(insight_score=90)
    low = _item(id="security_github_advisories:GHSA-1111-2222-3333", title="GHSA-1111-2222-3333", insight_score=10)
    ai = _item(domain="ai", insight_score=99)

    selected = select_candidates([low, ai, high], min_score=50, limit=5)

    assert selected == [(high, "GHSA-7q4f-pgqx-h3vh")]


@pytest.mark.asyncio
async def test_enqueue_candidates_inserts_without_committing_outer_transaction():
    session = FakeSession()

    enqueued = await enqueue_candidates(session, [_item()], min_score=50, limit=5)

    assert enqueued == ["GHSA-7q4f-pgqx-h3vh"]
    assert any(str(getattr(statement, "table", "")) == "deep_analyses" for statement in session.executed)
    assert session.commits == 0


@pytest.mark.asyncio
async def test_enqueue_candidates_skips_existing_non_failed_subjects():
    session = FakeSession(existing=["GHSA-7q4f-pgqx-h3vh"])

    enqueued = await enqueue_candidates(session, [_item()], min_score=50, limit=5)

    assert enqueued == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_enqueue_paper_inserts_without_committing_outer_transaction():
    session = FakeSession()

    subject = await enqueue_paper(session, "2512.07921", item_id="ai_arxiv:2512.07921")

    assert subject == "2512.07921"
    assert any(str(getattr(statement, "table", "")) == "deep_analyses" for statement in session.executed)
    assert session.commits == 0


@pytest.mark.asyncio
async def test_reset_stale_running_marks_old_claims_failed(monkeypatch):
    session = WorkerSession()
    monkeypatch.setattr(settings, "deep_analysis_stale_claim_timeout_hours", 1)
    monkeypatch.setattr(worker, "STALE_CLAIM_TIMEOUT", worker.timedelta(hours=1))

    changed = await worker._reset_stale_running(session, now=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc))

    assert changed == 1
    assert any("claimed_at <" in sql for sql in session.executed)
    assert session.commits == 1
