from __future__ import annotations

from collections.abc import Iterable

from src.ai.contracts import retention_bucket

SCORE_HISTOGRAM_BUCKETS = list(range(0, 100, 5))
RETENTION_BUCKET_KEYS = ["permanent", "30_days", "10_days", "5_days", "delete"]


def score_histogram(scores: Iterable[int | None]) -> dict[str, list[int]]:
    """Bucket scores into 5-point ranges for the dashboard histogram."""
    counts = [0 for _ in SCORE_HISTOGRAM_BUCKETS]
    for score in scores:
        if score is None:
            continue
        normalized = max(0, min(99, int(score)))
        index = normalized // 5
        counts[index] += 1
    return {"buckets": SCORE_HISTOGRAM_BUCKETS, "counts": counts}


def retention_bucket_counts(scores: Iterable[int | None]) -> dict[str, int]:
    """Count how many scores fall into each retention policy bucket."""
    counts = {key: 0 for key in RETENTION_BUCKET_KEYS}
    for score in scores:
        if score is None:
            continue
        counts[retention_bucket(score)] += 1
    return counts


def histogram_from_bucket_counts(bucket_counts: dict[int, int]) -> dict[str, list[int]]:
    """Expand sparse SQL bucket counts into the dashboard histogram contract."""
    counts = [bucket_counts.get(index, 0) for index, _bucket in enumerate(SCORE_HISTOGRAM_BUCKETS)]
    return {"buckets": SCORE_HISTOGRAM_BUCKETS, "counts": counts}


def retention_counts_from_bucket_counts(bucket_counts: dict[int, int]) -> dict[str, int]:
    """Derive retention buckets directly from histogram buckets without re-reading every score row."""
    return {
        "permanent": bucket_counts.get(15, 0) + bucket_counts.get(16, 0) + bucket_counts.get(17, 0) + bucket_counts.get(18, 0) + bucket_counts.get(19, 0),
        "30_days": bucket_counts.get(10, 0) + bucket_counts.get(11, 0) + bucket_counts.get(12, 0) + bucket_counts.get(13, 0) + bucket_counts.get(14, 0),
        "10_days": bucket_counts.get(6, 0) + bucket_counts.get(7, 0) + bucket_counts.get(8, 0) + bucket_counts.get(9, 0),
        "5_days": bucket_counts.get(2, 0) + bucket_counts.get(3, 0) + bucket_counts.get(4, 0) + bucket_counts.get(5, 0),
        "delete": bucket_counts.get(0, 0) + bucket_counts.get(1, 0),
    }
