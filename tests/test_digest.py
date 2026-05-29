from datetime import date, datetime, timezone

from src.pipeline.digest import DigestItem, beijing_digest_date, build_digest_artifact


def test_build_digest_artifact_groups_highlights_and_renders_hexo_markdown():
    generated_at = datetime(2026, 5, 26, 8, 6, tzinfo=timezone.utc)
    items = [
        DigestItem(
            id="security_nvd_cve:CVE-1",
            title="Critical Linux CVE",
            source_id="security_nvd_cve",
            category="vulnerability",
            summary_zh="Linux 内核高危漏洞。",
            insight_score=92,
            confidence="confirmed",
            action_suggestion="优先确认资产影响。",
        ),
        DigestItem(
            id="security_project_zero:p0-1",
            title="Browser exploit research",
            source_id="security_project_zero",
            category="research",
            summary_zh="浏览器利用研究。",
            insight_score=81,
            confidence="firm",
            action_suggestion="跟踪供应商修复。",
        ),
        DigestItem(
            id="security_portswigger:note-1",
            title="Moderate security note",
            source_id="security_portswigger",
            category="discussion",
            summary_zh="普通安全讨论。",
            insight_score=55,
            confidence=None,
        ),
        DigestItem(
            id="security_portswigger:low-1",
            title="Low score item",
            source_id="security_portswigger",
            category="discussion",
            summary_zh="低价值。",
            insight_score=39,
        ),
    ]

    artifact = build_digest_artifact(
        digest_date=date(2026, 5, 26),
        domain="security",
        items=items,
        collected_count=4,
        analyzed_count=4,
        failed_sources=1,
        overview="今日安全情报以漏洞披露和浏览器利用研究为主。",
        generated_at=generated_at,
    )

    assert artifact is not None
    assert artifact.id == "2026-05-26:security"
    assert artifact.title == "安全情报日报 · 2026-05-26"
    assert artifact.hexo_path == "intelligence-security-2026-05-26.md"
    assert artifact.stats_json == {"collected": 4, "analyzed": 4, "high_value": 2, "failed_sources": 1}
    assert artifact.highlights_json == [
        {"name": "research", "label": "研究分析", "count": 1, "item_ids": ["security_project_zero:p0-1"]},
        {"name": "vulnerability", "label": "漏洞披露", "count": 1, "item_ids": ["security_nvd_cve:CVE-1"]},
    ]
    assert "title: 安全情报日报 · 2026-05-26" in artifact.content_markdown
    assert "date: 2026-05-26 08:06:00" in artifact.content_markdown
    assert "## High Value" in artifact.content_markdown
    assert "- Moderate security note (score 55)" in artifact.content_markdown
    assert "Low score item" not in artifact.content_markdown


def test_build_digest_artifact_uses_template_overview_and_skips_empty_candidate_pool():
    artifact = build_digest_artifact(
        digest_date=date(2026, 5, 26),
        domain="ai",
        items=[
            DigestItem(
                id="ai_hackernews:1",
                title="Low score",
                source_id="ai_hackernews",
                category="discussion",
                summary_zh=None,
                insight_score=20,
            )
        ],
        collected_count=1,
        analyzed_count=1,
        failed_sources=0,
    )

    assert artifact is None

    artifact = build_digest_artifact(
        digest_date=date(2026, 5, 26),
        domain="ai",
        items=[
            DigestItem(
                id="ai_openai_blog:1",
                title="Model update",
                source_id="ai_openai_blog",
                category="product",
                summary_zh="模型更新。",
                insight_score=76,
            )
        ],
        collected_count=1,
        analyzed_count=1,
        failed_sources=0,
        generated_at=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
    )

    assert artifact is not None
    assert artifact.summary == "今日共采集 1 条情报，高价值 1 条。"
    assert artifact.title == "AI 情报日报 · 2026-05-26"


def test_beijing_digest_date_uses_user_facing_calendar_day():
    assert beijing_digest_date(datetime(2026, 5, 25, 16, 30, tzinfo=timezone.utc)) == date(2026, 5, 26)
