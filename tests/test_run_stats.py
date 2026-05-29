from src.pipeline.run_stats import (
    aggregate_digest_status,
    apply_source_stats,
    compute_progress,
    decide_final_run_status,
    digest_result,
    initial_run_stats,
    update_digest_stats,
)


def test_initial_run_stats_matches_pipeline_contract():
    stats = initial_run_stats(["security_nvd_cve", "ai_arxiv"])

    assert stats["sources"] == {
        "security_nvd_cve": {"status": "pending", "items": 0, "duration_s": 0.0},
        "ai_arxiv": {"status": "pending", "items": 0, "duration_s": 0.0},
    }
    assert stats["stage1"] == {"total": 0, "succeeded": 0, "failed": 0}
    assert stats["stage2"] == {"total": 0, "succeeded": 0, "failed": 0}
    assert stats["digest"] == {"status": "pending", "security": None, "ai": None}


def test_apply_source_stats_is_immutable_and_progress_uses_spec_weights():
    stats = initial_run_stats(["security_nvd_cve", "ai_arxiv"])
    updated = apply_source_stats(stats, "security_nvd_cve", {"status": "succeeded", "items": 5, "duration_s": 1.5})
    updated["stage1"] = {"total": 10, "succeeded": 5, "failed": 0}
    updated["stage2"] = {"total": 2, "succeeded": 1, "failed": 0}
    updated["digest"] = {"status": "partial", "security": None, "ai": None}

    assert stats["sources"]["security_nvd_cve"]["status"] == "pending"
    assert compute_progress(updated) == 0.55


def test_digest_aggregate_status_rules():
    ok = digest_result(status="succeeded", digest_id="2026-05-26:security")
    skipped = digest_result(status="skipped")
    failed = digest_result(status="failed", error="hexo_write_error")

    assert aggregate_digest_status(ok, skipped) == "succeeded"
    assert aggregate_digest_status(ok, failed) == "partial"
    assert aggregate_digest_status(failed, skipped) == "failed"
    assert aggregate_digest_status(skipped, skipped) == "failed"
    assert aggregate_digest_status(None, None) == "pending"


def test_update_digest_stats_sets_aggregate_status():
    stats = initial_run_stats(["security_nvd_cve"])
    security = digest_result(
        status="succeeded",
        digest_id="2026-05-26:security",
        hexo_path="intelligence-security-2026-05-26.md",
        oss_url="https://example.com/security.md",
    )

    updated = update_digest_stats(stats, security=security)

    assert updated["digest"]["security"] == security
    assert updated["digest"]["status"] == "succeeded"


def test_decide_final_run_status_matches_success_partial_failed_rules():
    stats = initial_run_stats(["security_nvd_cve", "ai_arxiv"])
    stats["sources"]["security_nvd_cve"] = {"status": "succeeded", "items": 5, "duration_s": 1.0}
    stats["sources"]["ai_arxiv"] = {"status": "succeeded", "items": 3, "duration_s": 1.0}
    stats["stage1"] = {"total": 8, "succeeded": 8, "failed": 0}
    stats["stage2"] = {"total": 2, "succeeded": 2, "failed": 0}
    stats["digest"] = {"status": "succeeded", "security": {"status": "succeeded"}, "ai": {"status": "skipped"}}

    assert decide_final_run_status(stats) == "succeeded"

    stats["sources"]["ai_arxiv"] = {"status": "failed", "items": 0, "duration_s": 30.0}
    assert decide_final_run_status(stats) == "partial"

    stats["sources"]["security_nvd_cve"] = {"status": "failed", "items": 0, "duration_s": 30.0}
    assert decide_final_run_status(stats) == "failed"


def test_decide_final_run_status_treats_fatal_digest_and_cleanup_failures_as_failed():
    stats = initial_run_stats(["security_nvd_cve"])
    stats["sources"]["security_nvd_cve"] = {"status": "succeeded", "items": 5, "duration_s": 1.0}
    stats["stage1"] = {"total": 5, "succeeded": 5, "failed": 0}
    stats["digest"] = {"status": "failed", "security": {"status": "failed"}, "ai": {"status": "skipped"}}

    assert decide_final_run_status(stats) == "failed"
    assert decide_final_run_status(stats, fatal_error="db_error") == "failed"
    assert decide_final_run_status(stats, cleanup_completed=False) == "failed"


def test_decide_final_run_status_marks_analysis_failures_partial_when_useful_output_exists():
    stats = initial_run_stats(["security_nvd_cve"])
    stats["sources"]["security_nvd_cve"] = {"status": "succeeded", "items": 5, "duration_s": 1.0}
    stats["stage1"] = {"total": 5, "succeeded": 4, "failed": 1}
    stats["stage2"] = {"total": 2, "succeeded": 1, "failed": 1}
    stats["digest"] = {"status": "succeeded", "security": {"status": "succeeded"}, "ai": {"status": "skipped"}}

    assert decide_final_run_status(stats) == "partial"
