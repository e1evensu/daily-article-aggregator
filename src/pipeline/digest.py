from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class DigestItem:
    id: str
    title: str
    source_id: str
    category: str
    summary_zh: str | None
    insight_score: int
    confidence: str | None = None
    action_suggestion: str | None = None


@dataclass(frozen=True)
class DigestArtifact:
    id: str
    date: date
    domain: str
    title: str
    summary: str
    stats_json: dict[str, Any]
    highlights_json: list[dict[str, Any]]
    content_markdown: str
    generated_at: datetime

    @property
    def hexo_path(self) -> str:
        return f"intelligence-{self.domain}-{self.date.isoformat()}.md"


CONFIDENCE_RANK = {"confirmed": 3, "firm": 2, "tentative": 1, None: 0}
CATEGORY_LABELS = {
    "vulnerability": "漏洞披露",
    "exploit": "武器化 / PoC",
    "research": "研究分析",
    "product": "产品发布",
    "engineering": "工程实践",
    "tool": "工具项目",
    "incident": "安全事件",
    "discussion": "社区讨论",
    "other": "其他",
}


def build_digest_artifact(
    *,
    digest_date: date,
    domain: str,
    items: list[DigestItem],
    collected_count: int,
    analyzed_count: int,
    failed_sources: int,
    overview: str | None = None,
    generated_at: datetime | None = None,
    candidate_threshold: int = 40,
    high_value_threshold: int = 75,
    top_n_per_category: int = 5,
) -> DigestArtifact | None:
    generated_at = _ensure_utc(generated_at or datetime.now(timezone.utc))
    candidate_items = [item for item in items if item.insight_score >= candidate_threshold]
    if not candidate_items:
        return None

    high_value_items = [item for item in candidate_items if item.insight_score >= high_value_threshold]
    lower_value_items = [item for item in candidate_items if item.insight_score < high_value_threshold]
    summary = overview or f"今日共采集 {collected_count} 条情报，高价值 {len(high_value_items)} 条。"
    title = _digest_title(domain, digest_date)
    highlights = _build_highlights(high_value_items, top_n_per_category)
    stats = {
        "collected": collected_count,
        "analyzed": analyzed_count,
        "high_value": len(high_value_items),
        "failed_sources": failed_sources,
    }
    content = render_digest_markdown(
        title=title,
        digest_date=digest_date,
        domain=domain,
        overview=summary,
        highlights=highlights,
        high_value_items=high_value_items,
        lower_value_items=lower_value_items,
        stats=stats,
        generated_at=generated_at,
    )

    return DigestArtifact(
        id=f"{digest_date.isoformat()}:{domain}",
        date=digest_date,
        domain=domain,
        title=title,
        summary=summary,
        stats_json=stats,
        highlights_json=highlights,
        content_markdown=content,
        generated_at=generated_at,
    )


def render_digest_markdown(
    *,
    title: str,
    digest_date: date,
    domain: str,
    overview: str,
    highlights: list[dict[str, Any]],
    high_value_items: list[DigestItem],
    lower_value_items: list[DigestItem],
    stats: dict[str, Any],
    generated_at: datetime,
) -> str:
    frontmatter = [
        "---",
        f"title: {title}",
        f"date: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
        "tags:",
        "  - intelligence",
        f"  - {domain}",
        "categories:",
        "  - 情报日报",
        "---",
        "",
    ]
    body = [
        "## Overview",
        "",
        overview,
        "",
        "## High Value",
        "",
    ]

    if high_value_items:
        by_id = {item.id: item for item in high_value_items}
        for group in highlights:
            body.extend([f"### {group['label']}", ""])
            for item_id in group["item_ids"]:
                item = by_id[item_id]
                body.extend(_render_high_value_item(item))
    else:
        body.extend(["暂无高价值情报。", ""])

    body.extend(["## Lower-value Mentions", ""])
    if lower_value_items:
        for item in _sort_digest_items(lower_value_items):
            body.append(f"- {item.title} (score {item.insight_score})")
    else:
        body.append("暂无。")

    body.extend([
        "",
        "## Stats",
        "",
        f"- Collected: {stats['collected']}",
        f"- Analyzed: {stats['analyzed']}",
        f"- High value: {stats['high_value']}",
        f"- Failed sources: {stats['failed_sources']}",
        "",
    ])

    return "\n".join(frontmatter + body)


def _build_highlights(items: list[DigestItem], top_n_per_category: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[DigestItem]] = defaultdict(list)
    for item in _sort_digest_items(items):
        grouped[item.category].append(item)

    highlights = []
    for category in sorted(grouped):
        category_items = grouped[category][:top_n_per_category]
        highlights.append(
            {
                "name": category,
                "label": CATEGORY_LABELS.get(category, category),
                "count": len(category_items),
                "item_ids": [item.id for item in category_items],
            }
        )
    return highlights


def _render_high_value_item(item: DigestItem) -> list[str]:
    lines = [
        f"- **{item.title}**",
        f"  - score: {item.insight_score}",
        f"  - source: {item.source_id}",
    ]
    if item.summary_zh:
        lines.append(f"  - summary: {item.summary_zh}")
    if item.action_suggestion:
        lines.append(f"  - action: {item.action_suggestion}")
    lines.append("")
    return lines


def _sort_digest_items(items: list[DigestItem]) -> list[DigestItem]:
    return sorted(
        items,
        key=lambda item: (
            -item.insight_score,
            -CONFIDENCE_RANK.get(item.confidence, 0),
            item.title,
            item.id,
        ),
    )


def _digest_title(domain: str, digest_date: date) -> str:
    prefix = "安全情报日报" if domain == "security" else "AI 情报日报" if domain == "ai" else "情报日报"
    return f"{prefix} · {digest_date.isoformat()}"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def beijing_digest_date(value: datetime) -> date:
    return value.astimezone(timezone(timedelta(hours=8))).date()
