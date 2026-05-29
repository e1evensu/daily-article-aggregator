from __future__ import annotations

from collections.abc import Iterable

from src.ai.contracts import retention_bucket

SCORE_HISTOGRAM_BUCKETS = list(range(0, 100, 5))
RETENTION_BUCKET_KEYS = ["permanent", "30_days", "10_days", "5_days", "delete"]


def score_histogram(scores: Iterable[int | None]) -> dict[str, list[int]]:
    counts = [0 for _ in SCORE_HISTOGRAM_BUCKETS]
    for score in scores:
        if score is None:
            continue
        normalized = max(0, min(99, int(score)))
        index = normalized // 5
        counts[index] += 1
    return {"buckets": SCORE_HISTOGRAM_BUCKETS, "counts": counts}


def retention_bucket_counts(scores: Iterable[int | None]) -> dict[str, int]:
    counts = {key: 0 for key in RETENTION_BUCKET_KEYS}
    for score in scores:
        if score is None:
            continue
        counts[retention_bucket(score)] += 1
    return counts
