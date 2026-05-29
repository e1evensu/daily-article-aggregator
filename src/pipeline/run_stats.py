from __future__ import annotations

from copy import deepcopy
from typing import Any


def initial_run_stats(source_ids: list[str]) -> dict[str, Any]:
    return {
        "sources": {source_id: {"status": "pending", "items": 0, "duration_s": 0.0} for source_id in source_ids},
        "stage1": {"total": 0, "succeeded": 0, "failed": 0},
        "stage2": {"total": 0, "succeeded": 0, "failed": 0},
        "dedup_skipped": 0,
        "retention_deleted": 0,
        "digest": {
            "status": "pending",
            "security": None,
            "ai": None,
        },
    }


def apply_source_stats(stats: dict[str, Any], source_id: str, source_stats: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(stats)
    updated.setdefault("sources", {})[source_id] = source_stats
    return updated


def compute_progress(stats: dict[str, Any] | None) -> float:
    if not stats:
        return 0.0

    sources = stats.get("sources", {})
    total_sources = len(sources)
    done_sources = sum(1 for source in sources.values() if source.get("status") in ("succeeded", "failed", "skipped"))

    stage1 = stats.get("stage1", {})
    stage2 = stats.get("stage2", {})
    digest = stats.get("digest", {})

    fetch_weight = (done_sources / total_sources * 0.3) if total_sources else 0.0
    stage1_weight = _ratio(stage1.get("succeeded", 0), stage1.get("total", 0)) * 0.4
    stage2_weight = _ratio(stage2.get("succeeded", 0), stage2.get("total", 0)) * 0.2
    digest_weight = 0.1 if digest.get("status") in ("succeeded", "partial") else 0.0

    return round(fetch_weight + stage1_weight + stage2_weight + digest_weight, 2)


def digest_result(
    *,
    status: str,
    digest_id: str | None = None,
    hexo_path: str | None = None,
    oss_url: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "digest_id": digest_id,
        "hexo_path": hexo_path,
        "oss_url": oss_url,
        "error": error,
    }


def aggregate_digest_status(security: dict[str, Any] | None, ai: dict[str, Any] | None) -> str:
    results = [result for result in (security, ai) if result is not None]
    if not results:
        return "pending"

    statuses = [result.get("status") for result in results]
    succeeded = statuses.count("succeeded")
    failed = statuses.count("failed")
    skipped = statuses.count("skipped")

    if succeeded and failed:
        return "partial"
    if succeeded and failed == 0:
        return "succeeded"
    if skipped == len(statuses):
        return "failed"
    if failed == len(statuses):
        return "failed"
    if failed and not succeeded:
        return "failed"
    return "pending"


def update_digest_stats(
    stats: dict[str, Any],
    *,
    security: dict[str, Any] | None = None,
    ai: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = deepcopy(stats)
    digest = dict(updated.get("digest") or {})
    if security is not None:
        digest["security"] = security
    if ai is not None:
        digest["ai"] = ai
    digest["status"] = aggregate_digest_status(digest.get("security"), digest.get("ai"))
    updated["digest"] = digest
    return updated


def decide_final_run_status(stats: dict[str, Any], *, fatal_error: str | None = None, cleanup_completed: bool = True) -> str:
    if fatal_error:
        return "failed"
    if not cleanup_completed:
        return "failed"

    source_statuses = [source.get("status") for source in stats.get("sources", {}).values()]
    source_succeeded = source_statuses.count("succeeded")
    source_failed = source_statuses.count("failed")
    if source_succeeded == 0:
        return "failed"

    stage1 = stats.get("stage1", {})
    if stage1.get("total", 0) and stage1.get("succeeded", 0) == 0:
        return "failed"

    digest_status = (stats.get("digest") or {}).get("status")
    if digest_status == "failed":
        return "failed"

    non_fatal_failure = (
        source_failed > 0
        or stage1.get("failed", 0) > 0
        or stats.get("stage2", {}).get("failed", 0) > 0
        or digest_status == "partial"
    )
    if non_fatal_failure:
        return "partial"

    if digest_status == "succeeded":
        return "succeeded"
    return "partial"


def _ratio(done: int, total: int) -> float:
    if not total:
        return 0.0
    return done / total
