from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from typing import Any

CATEGORY_VALUES = {
    "vulnerability",
    "exploit",
    "research",
    "product",
    "engineering",
    "tool",
    "incident",
    "discussion",
    "other",
}

CREDIBILITY_VALUES = {"high", "medium", "low", "unknown"}
CONFIDENCE_VALUES = {"tentative", "firm", "confirmed"}
TREND_SIGNAL_VALUES = {"emerging", "growing", "stable", "declining"}


class AnalysisParseError(ValueError):
    """Raised when model output cannot be accepted as the stage JSON contract."""


@dataclass(frozen=True)
class Stage1Analysis:
    category: str
    tags: list[str]
    summary_zh: str
    insight_score: int
    credibility: str


@dataclass(frozen=True)
class Stage2Analysis:
    recommendation_reason: str
    confidence: str
    trend_signal: str | None
    action_suggestion: str


@dataclass(frozen=True)
class DigestOverviewAnalysis:
    overview_zh: str


@dataclass(frozen=True)
class PreparedContent:
    content_text: str | None
    content_truncated: bool


def prepare_content_for_model(content_text: str | None) -> PreparedContent:
    """Trim oversized content while preserving enough head/tail context for the model."""
    if not content_text:
        return PreparedContent(content_text=content_text, content_truncated=False)
    if len(content_text) <= 4000:
        return PreparedContent(content_text=content_text, content_truncated=False)
    return PreparedContent(
        content_text=f"{content_text[:3000]}\n\n...[truncated]...\n\n{content_text[-500:]}",
        content_truncated=True,
    )


def parse_stage1_response(text: str) -> Stage1Analysis:
    """Parse and validate the stage-1 JSON response emitted by the model."""
    payload = _extract_json_object(text)
    score = _coerce_score(payload.get("insight_score"))
    summary = _require_string(payload, "summary_zh")

    category = str(payload.get("category", "other")).strip().lower()
    if category not in CATEGORY_VALUES:
        category = "other"

    credibility = str(payload.get("credibility", "unknown")).strip().lower()
    if credibility not in CREDIBILITY_VALUES:
        credibility = "unknown"

    return Stage1Analysis(
        category=category,
        tags=_coerce_tags(payload.get("tags")),
        summary_zh=summary,
        insight_score=score,
        credibility=credibility,
    )


def parse_stage2_response(text: str, source_authority: str, also_seen_in: list[dict[str, Any]] | None) -> Stage2Analysis:
    """Parse and validate the stage-2 JSON response, deriving confidence locally."""
    payload = _extract_json_object(text)
    trend_signal = payload.get("trend_signal")
    if trend_signal is not None:
        trend_signal = str(trend_signal).strip().lower()
        if trend_signal not in TREND_SIGNAL_VALUES:
            trend_signal = None

    return Stage2Analysis(
        recommendation_reason=_require_string(payload, "recommendation_reason"),
        confidence=derive_confidence(source_authority, also_seen_in),
        trend_signal=trend_signal,
        action_suggestion=_require_string(payload, "action_suggestion"),
    )


def parse_digest_overview_response(text: str) -> DigestOverviewAnalysis:
    """Parse and validate the digest overview JSON response emitted by the model."""
    payload = _extract_json_object(text)
    return DigestOverviewAnalysis(overview_zh=_require_string(payload, "overview_zh"))


def derive_confidence(source_authority: str, also_seen_in: list[dict[str, Any]] | None) -> str:
    """Derive confidence from source authority and corroborating source count."""
    is_official = source_authority == "official"
    corroboration_count = len(also_seen_in or [])

    if is_official and corroboration_count >= 1:
        return "confirmed"
    if corroboration_count >= 2:
        return "confirmed"
    if is_official or corroboration_count >= 1:
        return "firm"
    return "tentative"


def compute_expires_at(insight_score: int, analyzed_at: datetime) -> datetime | None:
    """Compute item expiry from the configured retention policy and insight score."""
    from src.config import settings

    analyzed_at = _ensure_utc(analyzed_at)
    score = max(0, min(100, int(insight_score)))

    if score < settings.retention_delete_below_score:
        return analyzed_at if settings.retention_below_10 <= 0 else analyzed_at + timedelta(days=settings.retention_below_10)
    if score < settings.retention_5_days_below_score:
        return analyzed_at + timedelta(days=settings.retention_below_30)
    if score < settings.retention_10_days_below_score:
        return analyzed_at + timedelta(days=settings.retention_below_50)
    if score < settings.stage2_threshold:
        return analyzed_at + timedelta(days=settings.retention_below_75)
    return None


def retention_bucket(insight_score: int) -> str:
    from src.config import settings

    score = max(0, min(100, int(insight_score)))
    if score < settings.retention_delete_below_score:
        return "delete"
    if score < settings.retention_5_days_below_score:
        return "5_days"
    if score < settings.retention_10_days_below_score:
        return "10_days"
    if score < settings.stage2_threshold:
        return "30_days"
    return "permanent"


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a raw model response."""
    cleaned = _strip_code_fence(text.strip())
    try:
        parsed = json.loads(cleaned)
    except JSONDecodeError:
        parsed = _scan_json_object(cleaned)

    if not isinstance(parsed, dict):
        raise AnalysisParseError("model response must be a JSON object")
    return parsed


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding markdown code fence if the model wrapped its JSON."""
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _scan_json_object(text: str) -> dict[str, Any]:
    """Scan free-form text for the first decodable JSON object."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise AnalysisParseError("model response does not contain valid JSON")


def _coerce_score(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        raise AnalysisParseError("insight_score must be numeric")
    try:
        return max(0, min(100, round(float(value))))
    except (TypeError, ValueError) as exc:
        raise AnalysisParseError("insight_score must be numeric") from exc


def _coerce_tags(value: Any) -> list[str]:
    """Normalize the model's tags field into a capped list of non-empty strings."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise AnalysisParseError("tags must be an array")
    tags = []
    for tag in value:
        text = str(tag).strip()
        if text:
            tags.append(text)
    return tags[:12]


def _require_string(payload: dict[str, Any], key: str) -> str:
    """Require one non-empty string field from the parsed JSON payload."""
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AnalysisParseError(f"{key} must be a non-empty string")
    return value.strip()


def _ensure_utc(value: datetime) -> datetime:
    """Normalize naive or local datetimes into UTC before persistence."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
