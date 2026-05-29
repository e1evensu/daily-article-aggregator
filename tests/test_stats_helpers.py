from src.api.stats_helpers import SCORE_HISTOGRAM_BUCKETS, retention_bucket_counts, score_histogram


def test_score_histogram_uses_five_point_buckets_and_ignores_missing_scores():
    histogram = score_histogram([None, -5, 0, 4, 5, 74, 75, 99, 100])

    assert histogram["buckets"] == SCORE_HISTOGRAM_BUCKETS
    assert histogram["counts"][0] == 3
    assert histogram["counts"][1] == 1
    assert histogram["counts"][14] == 1
    assert histogram["counts"][15] == 1
    assert histogram["counts"][19] == 2
    assert sum(histogram["counts"]) == 8


def test_retention_bucket_counts_match_spec_boundaries():
    counts = retention_bucket_counts([None, 0, 9, 10, 29, 30, 49, 50, 74, 75, 100])

    assert counts == {
        "permanent": 2,
        "30_days": 2,
        "10_days": 2,
        "5_days": 2,
        "delete": 2,
    }
