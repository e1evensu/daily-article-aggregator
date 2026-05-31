from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.ai.analyzer import Analyzer, should_run_stage2
from src.ai.client import ChatCompletionResult, OpenAICompatibleClient
from src.ai.contracts import (
    AnalysisParseError,
    compute_expires_at,
    derive_confidence,
    parse_digest_overview_response,
    parse_stage1_response,
    parse_stage2_response,
    prepare_content_for_model,
    retention_bucket,
)
from src.ai.prompts import (
    DIGEST_PROMPT_VERSION,
    STAGE1_PROMPT_VERSION,
    STAGE2_PROMPT_VERSION,
    build_digest_overview_messages,
    build_stage1_messages,
    build_stage2_messages,
)


class FakeCompleter:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = []

    async def complete(self, **kwargs):
        """Return queued fake model outputs while recording the completion call."""
        self.calls.append(kwargs)
        content = self.contents.pop(0)
        return ChatCompletionResult(provider="nvidia", model=kwargs["model"], content=content)


def test_parse_stage1_response_normalizes_spec_fields():
    result = parse_stage1_response(
        """
        ```json
        {
          "category": "unknown-category",
          "tags": ["cve", " linux ", ""],
          "summary_zh": "需要优先关注的 Linux 内核漏洞。",
          "insight_score": 130,
          "credibility": "invalid"
        }
        ```
        """
    )

    assert result.category == "other"
    assert result.tags == ["cve", "linux"]
    assert result.summary_zh == "需要优先关注的 Linux 内核漏洞。"
    assert result.insight_score == 100
    assert result.credibility == "unknown"


def test_parse_stage1_response_rejects_invalid_contract():
    with pytest.raises(AnalysisParseError):
        parse_stage1_response('{"category":"vulnerability","tags":[],"summary_zh":"缺少分数"}')


@pytest.mark.parametrize(
    ("authority", "also_seen_in", "expected"),
    [
        ("regular", [], "tentative"),
        ("official", [], "firm"),
        ("authoritative", [{"source_id": "security_portswigger"}], "firm"),
        ("official", [{"source_id": "security_github_advisories"}], "confirmed"),
        ("regular", [{"source_id": "a"}, {"source_id": "b"}], "confirmed"),
    ],
)
def test_derive_confidence_matches_pipeline_rules(authority, also_seen_in, expected):
    assert derive_confidence(authority, also_seen_in) == expected


def test_parse_stage2_response_uses_code_corrected_confidence_and_nulls_bad_trend():
    result = parse_stage2_response(
        """
        Some preface:
        {
          "recommendation_reason": "多源出现且影响面可能扩大。",
          "confidence": "tentative",
          "trend_signal": "surging",
          "action_suggestion": "跟踪补丁和利用代码。"
        }
        """,
        source_authority="official",
        also_seen_in=[{"source_id": "security_project_zero"}],
    )

    assert result.confidence == "confirmed"
    assert result.trend_signal is None
    assert result.recommendation_reason == "多源出现且影响面可能扩大。"
    assert result.action_suggestion == "跟踪补丁和利用代码。"


def test_parse_digest_overview_response_requires_overview_json():
    result = parse_digest_overview_response('{"overview_zh":"今日重点是漏洞披露，应优先确认影响面。"}')

    assert result.overview_zh == "今日重点是漏洞披露，应优先确认影响面。"

    with pytest.raises(AnalysisParseError):
        parse_digest_overview_response("今日重点是漏洞披露。")


@pytest.mark.parametrize(
    ("score", "bucket", "days"),
    [
        (9, "delete", 0),
        (10, "5_days", 5),
        (30, "10_days", 10),
        (50, "30_days", 30),
    ],
)
def test_retention_rules(score, bucket, days):
    analyzed_at = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)

    assert retention_bucket(score) == bucket
    expected = analyzed_at if days == 0 else analyzed_at + timedelta(days=days)
    assert compute_expires_at(score, analyzed_at) == expected


def test_high_score_retention_is_permanent():
    analyzed_at = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)

    assert retention_bucket(75) == "permanent"
    assert compute_expires_at(75, analyzed_at) is None


def test_prepare_content_for_model_uses_spec_truncation_policy():
    content = "a" * 4500
    prepared = prepare_content_for_model(content)

    assert prepared.content_truncated is True
    assert prepared.content_text is not None
    assert prepared.content_text.startswith("a" * 3000)
    assert prepared.content_text.endswith("a" * 500)


def test_prompt_builders_include_versions_and_json_contracts():
    item = {
        "title": "Example CVE",
        "canonical_url": "https://example.com/cve",
        "content_text": "details",
        "summary_zh": "摘要",
        "category": "vulnerability",
        "insight_score": 82,
        "credibility": "high",
    }
    source = {"name": "NVD", "authority": "official"}

    stage1_messages = build_stage1_messages(item, source)
    stage2_messages = build_stage2_messages(item, source, [{"source_id": "security_github_advisories"}])
    digest_messages = build_digest_overview_messages("security", [item])

    assert STAGE1_PROMPT_VERSION == "s1_v1"
    assert STAGE2_PROMPT_VERSION == "s2_v1"
    assert DIGEST_PROMPT_VERSION == "digest_v1"
    assert "stage1_analysis" in stage1_messages[1]["content"]
    assert "vulnerability" in stage1_messages[1]["content"]
    assert "stage2_analysis" in stage2_messages[1]["content"]
    assert "trend_signal" in stage2_messages[1]["content"]
    assert "digest_overview" in digest_messages[1]["content"]
    assert "overview_zh" in digest_messages[1]["content"]


@pytest.mark.asyncio
async def test_analyzer_retries_stage1_parse_once_and_sets_retention_metadata():
    now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
    completer = FakeCompleter([
        "not json",
        '{"category":"vulnerability","tags":["cve"],"summary_zh":"摘要","insight_score":88,"credibility":"high"}',
    ])
    analyzer = Analyzer(
        completer,
        stage1_model="deepseek-ai/deepseek-v4-flash",
        stage2_model="deepseek-ai/deepseek-v4-pro",
        now_fn=lambda: now,
    )

    outcome = await analyzer.analyze_stage1({"title": "CVE", "content_text": "details"}, {"authority": "official"})

    assert outcome.error is None
    assert outcome.analysis is not None
    assert outcome.analysis.insight_score == 88
    assert outcome.provider == "nvidia"
    assert outcome.prompt_version == STAGE1_PROMPT_VERSION
    assert outcome.expires_at is None
    assert len(completer.calls) == 2
    assert "valid JSON only" in completer.calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_analyzer_returns_model_parse_error_after_stage1_repair_failure():
    completer = FakeCompleter(["not json", "still not json"])
    analyzer = Analyzer(
        completer,
        stage1_model="deepseek-ai/deepseek-v4-flash",
        stage2_model="deepseek-ai/deepseek-v4-pro",
    )

    outcome = await analyzer.analyze_stage1({"title": "CVE"}, {"authority": "official"})

    assert outcome.analysis is None
    assert outcome.error == "model_parse_error"
    assert len(completer.calls) == 2


@pytest.mark.asyncio
async def test_analyzer_stage2_corrects_model_confidence():
    completer = FakeCompleter([
        """
        {
          "recommendation_reason": "官方来源且被多处引用。",
          "confidence": "tentative",
          "trend_signal": "growing",
          "action_suggestion": "优先确认影响资产。"
        }
        """
    ])
    analyzer = Analyzer(
        completer,
        stage1_model="deepseek-ai/deepseek-v4-flash",
        stage2_model="deepseek-ai/deepseek-v4-pro",
    )

    outcome = await analyzer.analyze_stage2(
        {"title": "CVE", "summary_zh": "摘要", "insight_score": 90},
        {"authority": "official"},
        [{"source_id": "security_github_advisories"}],
    )

    assert outcome.error is None
    assert outcome.analysis is not None
    assert outcome.analysis.confidence == "confirmed"
    assert outcome.analysis.trend_signal == "growing"
    assert outcome.prompt_version == STAGE2_PROMPT_VERSION


@pytest.mark.asyncio
async def test_analyzer_digest_overview_retries_parse_once():
    completer = FakeCompleter([
        "not json",
        '{"overview_zh":"今日安全情报以高危漏洞为主，应优先确认资产影响。"}',
    ])
    analyzer = Analyzer(
        completer,
        stage1_model="deepseek-ai/deepseek-v4-flash",
        stage2_model="deepseek-ai/deepseek-v4-pro",
    )

    outcome = await analyzer.generate_digest_overview(
        "security",
        [{"title": "CVE", "summary_zh": "摘要", "category": "vulnerability", "insight_score": 90}],
    )

    assert outcome.error is None
    assert outcome.analysis is not None
    assert outcome.analysis.overview_zh == "今日安全情报以高危漏洞为主，应优先确认资产影响。"
    assert outcome.prompt_version == DIGEST_PROMPT_VERSION
    assert len(completer.calls) == 2
    assert completer.calls[0]["model"] == "deepseek-ai/deepseek-v4-flash"
    assert completer.calls[0]["max_tokens"] == 1024
    assert completer.calls[0]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_analyzer_digest_overview_returns_parse_error_after_repair_failure():
    completer = FakeCompleter(["not json", "still not json"])
    analyzer = Analyzer(
        completer,
        stage1_model="deepseek-ai/deepseek-v4-flash",
        stage2_model="deepseek-ai/deepseek-v4-pro",
    )

    outcome = await analyzer.generate_digest_overview("ai", [])

    assert outcome.analysis is None
    assert outcome.error == "model_parse_error"


def test_should_run_stage2_uses_spec_threshold():
    assert should_run_stage2(None) is False
    assert should_run_stage2(74) is False
    assert should_run_stage2(75) is True


@pytest.mark.asyncio
async def test_openai_client_falls_back_from_max_tokens_to_max_completion_tokens():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(400, json={"error": {"message": "max_tokens unsupported"}})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://example.test/v1",
        api_key="test-key",
        provider="nvidia",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await client.complete(
            model="deepseek-ai/deepseek-v4-flash",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.1,
            max_tokens=2048,
            timeout_s=5,
            retries=0,
            retry_backoff_s=(),
        )
    finally:
        await client.aclose()

    assert result.provider == "nvidia"
    assert result.content == '{"ok": true}'
    assert '"max_tokens"' in requests[0]
    assert '"max_completion_tokens"' in requests[1]
    assert '"max_tokens"' not in requests[1]
