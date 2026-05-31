from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


class AIClientError(RuntimeError):
    def __init__(self, category: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.retryable = retryable


@dataclass(frozen=True)
class ChatCompletionResult:
    provider: str
    model: str
    content: str


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        provider: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.provider = provider
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            transport=transport,
        )

    @classmethod
    def nvidia_from_settings(cls) -> OpenAICompatibleClient:
        """Build a client pointed at the configured NVIDIA-compatible endpoint."""
        from src.config import settings

        return cls(
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key,
            provider="nvidia",
        )

    async def aclose(self) -> None:
        """Close the underlying async HTTP client."""
        await self._client.aclose()

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
        """Request one completion and normalize provider quirks around token fields."""
        base_payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        token_fields: list[str | None] = ["max_tokens", "max_completion_tokens", None] if max_tokens else [None]
        last_error: AIClientError | None = None

        for token_field in token_fields:
            payload = dict(base_payload)
            if token_field:
                payload[token_field] = max_tokens

            try:
                data = await self._post_with_retries(payload, timeout_s, retries, retry_backoff_s)
                return ChatCompletionResult(
                    provider=self.provider,
                    model=model,
                    content=_extract_message_content(data),
                )
            except AIClientError as exc:
                last_error = exc
                if _is_token_parameter_rejection(exc, token_field):
                    continue
                raise

        if last_error:
            raise last_error
        raise AIClientError("model_provider_error", "completion request failed")

    async def _post_with_retries(
        self,
        payload: dict[str, Any],
        timeout_s: float,
        retries: int,
        retry_backoff_s: tuple[float, ...],
    ) -> dict[str, Any]:
        """Send a completion request with retry/backoff handling."""
        for attempt in range(retries + 1):
            try:
                return await self._post_once(payload, timeout_s)
            except AIClientError as exc:
                if not exc.retryable or attempt >= retries:
                    raise
                await asyncio.sleep(_backoff_for_attempt(retry_backoff_s, attempt))
        raise AIClientError("model_provider_error", "completion retries exhausted")

    async def _post_once(self, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        """Send one raw completion request and normalize HTTP errors."""
        try:
            response = await self._client.post("/chat/completions", json=payload, timeout=timeout_s)
        except httpx.TimeoutException as exc:
            raise AIClientError("model_timeout", str(exc), retryable=True) from exc
        except httpx.HTTPError as exc:
            raise AIClientError("model_provider_error", str(exc), retryable=True) from exc

        if response.status_code == 429:
            raise AIClientError("model_rate_limited", response.text, retryable=True)
        if response.status_code >= 500:
            raise AIClientError("model_provider_error", response.text, retryable=True)
        if response.status_code >= 400:
            raise AIClientError("model_provider_error", response.text, retryable=False)

        try:
            return response.json()
        except ValueError as exc:
            raise AIClientError("model_provider_error", "completion response is not JSON") from exc


def _extract_message_content(data: dict[str, Any]) -> str:
    """Extract the assistant message body from an OpenAI-compatible completion response."""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIClientError("model_provider_error", "completion response missing message content") from exc

    if not isinstance(content, str) or not content.strip():
        raise AIClientError("model_provider_error", "completion response content is empty")
    return content


def _is_token_parameter_rejection(exc: AIClientError, token_field: str | None) -> bool:
    """Detect provider errors caused by unsupported max-token parameter names."""
    if exc.category != "model_provider_error" or exc.retryable or not token_field:
        return False
    message = str(exc).lower()
    return token_field.lower() in message and ("unsupported" in message or "unknown" in message or "invalid" in message)


def _backoff_for_attempt(backoff_s: tuple[float, ...], attempt: int) -> float:
    """Pick the configured retry backoff for the current attempt index."""
    if not backoff_s:
        return 0.0
    return backoff_s[min(attempt, len(backoff_s) - 1)]
