from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.ai.contracts import CATEGORY_VALUES, prepare_content_for_model

STAGE1_PROMPT_VERSION = "s1_v1"
STAGE2_PROMPT_VERSION = "s2_v1"
DIGEST_PROMPT_VERSION = "digest_v1"

_CATEGORY_NOTES = {
    "vulnerability": "CVE, GHSA, vendor advisory, or vulnerability disclosure",
    "exploit": "weaponization, PoC, exploit code, or Metasploit module",
    "research": "paper, technical blog, or long-form analysis",
    "product": "model, product, release, or version update",
    "engineering": "architecture, production practice, or technical decision",
    "tool": "new tool, open-source project, framework, or library update",
    "incident": "breach, attack, threat intelligence, or operational security event",
    "discussion": "community discussion, opinion thread, or debate",
    "other": "fallback when no category fits",
}


def build_stage1_messages(item: dict[str, Any], source: dict[str, Any]) -> list[dict[str, str]]:
    prepared = prepare_content_for_model(item.get("content_text"))
    payload = {
        "title": item.get("title"),
        "canonical_url": item.get("canonical_url"),
        "source_name": source.get("name"),
        "source_authority": source.get("authority"),
        "published_at": _isoformat(item.get("published_at")),
        "content_text": prepared.content_text,
        "content_truncated": prepared.content_truncated,
    }
    return [
        {
            "role": "system",
            "content": (
                "You classify one intelligence item. Respond with valid JSON only. "
                "Use Chinese for summary_zh. Do not include markdown."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "stage1_analysis",
                    "schema": {
                        "category": sorted(CATEGORY_VALUES),
                        "tags": "array of short strings",
                        "summary_zh": "Chinese summary, <= 500 chars",
                        "insight_score": "integer 0-100",
                        "credibility": ["high", "medium", "low", "unknown"],
                    },
                    "category_notes": _CATEGORY_NOTES,
                    "item": payload,
                },
                ensure_ascii=False,
            ),
        },
    ]


def build_stage2_messages(
    item: dict[str, Any],
    source: dict[str, Any],
    also_seen_in: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    payload = {
        "title": item.get("title"),
        "canonical_url": item.get("canonical_url"),
        "category": item.get("category"),
        "tags": item.get("tags") or [],
        "summary_zh": item.get("summary_zh"),
        "insight_score": item.get("insight_score"),
        "credibility": item.get("credibility"),
        "source_name": source.get("name"),
        "source_authority": source.get("authority"),
        "also_seen_in": also_seen_in or [],
    }
    return [
        {
            "role": "system",
            "content": (
                "You produce a second-stage intelligence recommendation. "
                "Respond with valid JSON only. Do not include markdown."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "stage2_analysis",
                    "schema": {
                        "recommendation_reason": "why this is worth attention",
                        "confidence": ["tentative", "firm", "confirmed"],
                        "trend_signal": ["emerging", "growing", "stable", "declining"],
                        "action_suggestion": "concrete next action",
                    },
                    "trend_signal_notes": {
                        "emerging": "newly disclosed or early signal",
                        "growing": "attention or impact is increasing",
                        "stable": "known issue or steady discussion",
                        "declining": "mature mitigations or reduced attention",
                    },
                    "item": payload,
                },
                ensure_ascii=False,
            ),
        },
    ]


def build_digest_overview_messages(domain: str, items: list[dict[str, Any]]) -> list[dict[str, str]]:
    payload = {
        "domain": domain,
        "items": [
            {
                "title": item.get("title"),
                "category": item.get("category"),
                "summary_zh": item.get("summary_zh"),
                "insight_score": item.get("insight_score"),
                "action_suggestion": item.get("action_suggestion"),
            }
            for item in items[:20]
        ],
    }
    return [
        {
            "role": "system",
            "content": (
                "You write a concise Chinese daily intelligence digest overview. "
                "Respond with valid JSON only. Do not include markdown."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "digest_overview",
                    "schema": {
                        "overview_zh": "2-3 Chinese sentences summarizing key signals and priority actions",
                    },
                    "input_rules": [
                        "Base the overview only on the provided high-value items.",
                        "Mention the most important themes and recommended priority if clear.",
                        "Keep it concise and suitable for the Overview section of a daily report.",
                    ],
                    "digest": payload,
                },
                ensure_ascii=False,
            ),
        },
    ]


def _isoformat(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value:
        return str(value)
    return None
