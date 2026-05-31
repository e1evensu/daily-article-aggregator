from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from src.ai.client import AIClientError, ChatCompletionResult, OpenAICompatibleClient
from src.ai.contracts import (
    AnalysisParseError,
    DigestOverviewAnalysis,
    Stage1Analysis,
    Stage2Analysis,
    compute_expires_at,
    parse_digest_overview_response,
    parse_stage1_response,
    parse_stage2_response,
)
from src.ai.prompts import (
    DIGEST_PROMPT_VERSION,
    STAGE1_PROMPT_VERSION,
    STAGE2_PROMPT_VERSION,
    build_digest_overview_messages,
    build_stage1_messages,
    build_stage2_messages,
)
from src.config import parse_float_tuple


class ChatCompleter(Protocol):
    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
        timeout_s: float,
        retries: int,
        retry_backoff_s: tuple[float, ...],
    ) -> ChatCompletionResult:
        """Return one chat completion result for the supplied model and prompt."""
        ...


@dataclass(frozen=True)
class ModelPolicy:
    timeout_s: float
    retries: int
    retry_backoff_s: tuple[float, ...]
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class Stage1Outcome:
    analysis: Stage1Analysis | None
    provider: str | None
    model: str
    prompt_version: str
    analyzed_at: datetime
    expires_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class Stage2Outcome:
    analysis: Stage2Analysis | None
    provider: str | None
    model: str
    prompt_version: str
    analyzed_at: datetime
    error: str | None


@dataclass(frozen=True)
class DigestOverviewOutcome:
    analysis: DigestOverviewAnalysis | None
    provider: str | None
    model: str
    prompt_version: str
    analyzed_at: datetime
    error: str | None


STAGE1_POLICY = ModelPolicy(
    timeout_s=120.0,
    retries=2,
    retry_backoff_s=(2.0, 4.0),
    temperature=0.1,
    max_tokens=2048,
)

STAGE2_POLICY = ModelPolicy(
    timeout_s=300.0,
    retries=2,
    retry_backoff_s=(5.0, 10.0),
    temperature=0.2,
    max_tokens=4096,
)

DIGEST_POLICY = ModelPolicy(
    timeout_s=300.0,
    retries=2,
    retry_backoff_s=(2.0, 4.0),
    temperature=0.3,
    max_tokens=1024,
)


def model_policy_from_settings(stage: str) -> ModelPolicy:
    from src.config import settings

    return ModelPolicy(
        timeout_s=getattr(settings, f"{stage}_timeout_s"),
        retries=getattr(settings, f"{stage}_retries"),
        retry_backoff_s=parse_float_tuple(getattr(settings, f"{stage}_retry_backoff_s")),
        temperature=getattr(settings, f"{stage}_temperature"),
        max_tokens=getattr(settings, f"{stage}_max_tokens"),
    )


def should_run_stage2(insight_score: int | None, threshold: int | None = None) -> bool:
    if threshold is None:
        from src.config import settings

        threshold = settings.stage2_threshold
    return insight_score is not None and insight_score >= threshold


class Analyzer:
    def __init__(
        self,
        client: ChatCompleter,
        *,
        stage1_model: str,
        stage2_model: str,
        digest_model: str | None = None,
        stage1_policy: ModelPolicy = STAGE1_POLICY,
        stage2_policy: ModelPolicy = STAGE2_POLICY,
        digest_policy: ModelPolicy = DIGEST_POLICY,
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.client = client
        self.stage1_model = stage1_model
        self.stage2_model = stage2_model
        self.digest_model = digest_model or stage1_model
        self.stage1_policy = stage1_policy
        self.stage2_policy = stage2_policy
        self.digest_policy = digest_policy
        self._now_fn = now_fn or _utc_now

    @classmethod
    def nvidia_from_settings(cls) -> Analyzer:
        """Build an Analyzer wired to the configured NVIDIA-compatible chat backend."""
        from src.config import settings

        return cls(
            OpenAICompatibleClient.nvidia_from_settings(),
            stage1_model=settings.stage1_model,
            stage2_model=settings.stage2_model,
            digest_model=settings.digest_model,
            stage1_policy=model_policy_from_settings("stage1"),
            stage2_policy=model_policy_from_settings("stage2"),
            digest_policy=model_policy_from_settings("digest"),
        )

    async def analyze_stage1(self, item: dict[str, Any], source: dict[str, Any]) -> Stage1Outcome:
        """Run stage-1 analysis and normalize provider or parsing failures into outcomes."""
        analyzed_at = _ensure_utc(self._now_fn())
        messages = build_stage1_messages(item, source)

        try:
            result = await self._complete(self.stage1_model, messages, self.stage1_policy)
            try:
                analysis = parse_stage1_response(result.content)
            except AnalysisParseError:
                result = await self._complete(
                    self.stage1_model,
                    _repair_messages(messages, result.content),
                    self.stage1_policy,
                )
                analysis = parse_stage1_response(result.content)
        except AnalysisParseError:
            return Stage1Outcome(
                analysis=None,
                provider=None,
                model=self.stage1_model,
                prompt_version=STAGE1_PROMPT_VERSION,
                analyzed_at=analyzed_at,
                expires_at=None,
                error="model_parse_error",
            )
        except AIClientError as exc:
            return Stage1Outcome(
                analysis=None,
                provider=None,
                model=self.stage1_model,
                prompt_version=STAGE1_PROMPT_VERSION,
                analyzed_at=analyzed_at,
                expires_at=None,
                error=exc.category,
            )

        return Stage1Outcome(
            analysis=analysis,
            provider=result.provider,
            model=result.model,
            prompt_version=STAGE1_PROMPT_VERSION,
            analyzed_at=analyzed_at,
            expires_at=compute_expires_at(analysis.insight_score, analyzed_at),
            error=None,
        )

    async def analyze_stage2(
        self,
        item: dict[str, Any],
        source: dict[str, Any],
        also_seen_in: list[dict[str, Any]] | None = None,
    ) -> Stage2Outcome:
        """Run stage-2 analysis and normalize provider or parsing failures into outcomes."""
        analyzed_at = _ensure_utc(self._now_fn())
        messages = build_stage2_messages(item, source, also_seen_in)
        source_authority = str(source.get("authority") or "regular")

        try:
            result = await self._complete(self.stage2_model, messages, self.stage2_policy)
            try:
                analysis = parse_stage2_response(result.content, source_authority, also_seen_in)
            except AnalysisParseError:
                result = await self._complete(
                    self.stage2_model,
                    _repair_messages(messages, result.content),
                    self.stage2_policy,
                )
                analysis = parse_stage2_response(result.content, source_authority, also_seen_in)
        except AnalysisParseError:
            return Stage2Outcome(
                analysis=None,
                provider=None,
                model=self.stage2_model,
                prompt_version=STAGE2_PROMPT_VERSION,
                analyzed_at=analyzed_at,
                error="model_parse_error",
            )
        except AIClientError as exc:
            return Stage2Outcome(
                analysis=None,
                provider=None,
                model=self.stage2_model,
                prompt_version=STAGE2_PROMPT_VERSION,
                analyzed_at=analyzed_at,
                error=exc.category,
            )

        return Stage2Outcome(
            analysis=analysis,
            provider=result.provider,
            model=result.model,
            prompt_version=STAGE2_PROMPT_VERSION,
            analyzed_at=analyzed_at,
            error=None,
        )

    async def generate_digest_overview(self, domain: str, items: list[dict[str, Any]]) -> DigestOverviewOutcome:
        """Generate the overview paragraph used at the top of a daily digest."""
        analyzed_at = _ensure_utc(self._now_fn())
        messages = build_digest_overview_messages(domain, items)

        try:
            result = await self._complete(self.digest_model, messages, self.digest_policy)
            try:
                analysis = parse_digest_overview_response(result.content)
            except AnalysisParseError:
                result = await self._complete(
                    self.digest_model,
                    _repair_messages(messages, result.content),
                    self.digest_policy,
                )
                analysis = parse_digest_overview_response(result.content)
        except AnalysisParseError:
            return DigestOverviewOutcome(
                analysis=None,
                provider=None,
                model=self.digest_model,
                prompt_version=DIGEST_PROMPT_VERSION,
                analyzed_at=analyzed_at,
                error="model_parse_error",
            )
        except AIClientError as exc:
            return DigestOverviewOutcome(
                analysis=None,
                provider=None,
                model=self.digest_model,
                prompt_version=DIGEST_PROMPT_VERSION,
                analyzed_at=analyzed_at,
                error=exc.category,
            )

        return DigestOverviewOutcome(
            analysis=analysis,
            provider=result.provider,
            model=result.model,
            prompt_version=DIGEST_PROMPT_VERSION,
            analyzed_at=analyzed_at,
            error=None,
        )

    async def _complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        policy: ModelPolicy,
    ) -> ChatCompletionResult:
        """Dispatch one completion request using the supplied model and policy."""
        return await self.client.complete(
            model=model,
            messages=messages,
            temperature=policy.temperature,
            max_tokens=policy.max_tokens,
            timeout_s=policy.timeout_s,
            retries=policy.retries,
            retry_backoff_s=policy.retry_backoff_s,
        )


def _repair_messages(messages: list[dict[str, str]], invalid_content: str) -> list[dict[str, str]]:
    """Append a repair turn that asks the model to re-emit valid JSON only."""
    return [
        *messages,
        {"role": "assistant", "content": invalid_content},
        {
            "role": "user",
            "content": (
                "The previous response did not satisfy the JSON schema. "
                "Respond with valid JSON only, with no markdown or commentary."
            ),
        },
    ]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime) -> datetime:
    """Normalize naive or local datetimes into UTC before storing analysis timestamps."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
