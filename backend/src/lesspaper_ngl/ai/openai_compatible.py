"""OpenAI-compatible chat and embedding adapter."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from lesspaper_ngl.ai.base import (
    AIProviderAdapter,
    AIProviderError,
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ModelCapabilities,
)
from lesspaper_ngl.ai.provider_lock import provider_host_lock
from lesspaper_ngl.ai.retry import (
    ADAPTER_RETRY_ATTEMPTS,
    adapter_retry_delay_seconds,
    is_transient_ai_error,
)
from lesspaper_ngl.models import AIProvider


def _normalize_base_url(base_url: str) -> str:
    """Normalize to an OpenAI-compatible root ending with ``/v1/``.

    Accepts both ``https://host`` and ``https://host/v1``.
    """
    raw = base_url.strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AIProviderError(f"Invalid provider base URL: {base_url}")

    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[: -len("/v1")]
    # Drop accidental duplicated /v1 segments
    while path.endswith("/v1"):
        path = path[: -len("/v1")]
    path = f"{path}/v1/" if path else "/v1/"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message
            if error.get("code") is not None:
                return str(error.get("code"))
        if isinstance(error, str) and error.strip():
            return error
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message

    return str(payload)


def _usage_cost(usage: dict[str, Any]) -> float | None:
    """Read the optional OpenRouter/OpenAI-compatible cost field safely."""
    value = usage.get("cost")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


class OpenAICompatibleAdapter(AIProviderAdapter):
    """Async client for /v1/chat/completions and /v1/embeddings APIs."""

    def __init__(
        self,
        provider: AIProvider,
        api_key: str | None = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._base_url = _normalize_base_url(provider.base_url)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
        )

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def is_local(self) -> bool:
        return self._provider.is_local

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            supports_chat=True,
            supports_embeddings=self._provider.supports_embeddings,
            supports_vision=self._provider.supports_vision,
            context_window=self._provider.context_window,
            max_output_tokens=self._provider.max_output_tokens,
        )

    def _resolve_chat_model(self, model: str | None) -> str:
        resolved = model or self._provider.chat_model
        if not resolved:
            raise AIProviderError("No chat model configured for provider.")
        return resolved

    def _resolve_embedding_model(self, model: str | None) -> str:
        resolved = model or self._provider.embedding_model
        if not resolved:
            raise AIProviderError("No embedding model configured for provider.")
        return resolved

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        # Local hosts (LM Studio, etc.) serialize requests so chat/embed model
        # swaps cannot unload each other mid-flight. Hold the lock across
        # transient retries so a competing job cannot thrash the same host.
        lock = provider_host_lock(self._base_url) if self.is_local else nullcontext()
        async with lock:
            return await self._request_with_retries(method, path, payload=payload)

    async def _request_with_retries(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        last_error: AIProviderError | None = None
        for attempt in range(1, ADAPTER_RETRY_ATTEMPTS + 1):
            try:
                return await self._request_once(method, path, payload=payload)
            except AIProviderError as exc:
                last_error = exc
                if not is_transient_ai_error(exc) or attempt >= ADAPTER_RETRY_ATTEMPTS:
                    raise
                await asyncio.sleep(adapter_retry_delay_seconds(attempt))
        assert last_error is not None
        raise last_error

    async def _request_once(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        try:
            response = await self._client.request(method, path, json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                f"Request to {self._provider.name} timed out.",
                status_code=408,
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                f"Network error contacting {self._provider.name}: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise AIProviderError(
                _extract_error_message(response),
                status_code=response.status_code,
            )

        if response.status_code == 204 or not response.content:
            return {}

        try:
            data = response.json()
        except ValueError as exc:
            raise AIProviderError("Provider returned invalid JSON.") from exc
        return data

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        resolved_model = self._resolve_chat_model(model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "temperature": temperature,
        }
        token_limit = max_tokens or self._provider.max_output_tokens
        if token_limit is not None:
            payload["max_tokens"] = token_limit

        data = await self._request("POST", "chat/completions", payload=payload)
        if not isinstance(data, dict):
            raise AIProviderError("Provider returned an unexpected response payload.")

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AIProviderError("Chat completion response missing choices.")

        first = choices[0]
        if not isinstance(first, dict):
            raise AIProviderError("Chat completion choice has invalid shape.")

        message = first.get("message")
        if not isinstance(message, dict):
            raise AIProviderError("Chat completion response missing message.")

        content = message.get("content")
        finish_reason = first.get("finish_reason")
        finish_reason_str = finish_reason if isinstance(finish_reason, str) else None

        if not isinstance(content, str) or not content.strip():
            # Reasoning models (e.g. Qwen3 thinking) may return empty content and
            # put the visible answer in reasoning_content. If finish_reason is
            # "length", the model ran out of tokens mid-thought — that truncated
            # reasoning is not a usable answer; fail clearly so callers raise the budget.
            reasoning = message.get("reasoning_content")
            if finish_reason_str == "length":
                raise AIProviderError(
                    "Chat completion truncated before producing content "
                    "(thinking model exhausted max_tokens). "
                    "Increase the provider max_output_tokens."
                )
            if isinstance(reasoning, str) and reasoning.strip():
                content = reasoning
            else:
                raise AIProviderError("Chat completion response missing content.")

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        reported_cost = _usage_cost(usage)

        return ChatResult(
            content=content,
            model=str(data.get("model", resolved_model)),
            input_tokens=_coerce_int(usage.get("prompt_tokens")),
            output_tokens=_coerce_int(usage.get("completion_tokens")),
            reported_cost=reported_cost,
            cost_currency="USD" if reported_cost is not None else None,
            finish_reason=finish_reason_str,
            raw=data,
        )

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        if not texts:
            raise AIProviderError("At least one text is required for embedding.")

        resolved_model = self._resolve_embedding_model(model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "input": texts if len(texts) > 1 else texts[0],
        }

        data = await self._request("POST", "embeddings", payload=payload)
        if not isinstance(data, dict):
            raise AIProviderError("Provider returned an unexpected response payload.")

        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise AIProviderError("Embedding response missing data.")

        sorted_items = sorted(
            (item for item in items if isinstance(item, dict)),
            key=lambda item: int(item.get("index", 0)),
        )
        embeddings: list[list[float]] = []
        for item in sorted_items:
            vector = item.get("embedding")
            if not isinstance(vector, list):
                raise AIProviderError("Embedding response item missing embedding vector.")
            embeddings.append([float(value) for value in vector])

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        reported_cost = _usage_cost(usage)

        return EmbeddingResult(
            embeddings=embeddings,
            model=str(data.get("model", resolved_model)),
            input_tokens=_coerce_int(usage.get("prompt_tokens") or usage.get("total_tokens")),
            reported_cost=reported_cost,
            cost_currency="USD" if reported_cost is not None else None,
            raw=data,
        )

    async def test_connection(self) -> bool:
        """Prefer /models (cheap). Fall back to a tiny chat/embed call."""
        try:
            data = await self._request("GET", "models")
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                return True
            if isinstance(data, list):
                return True
        except AIProviderError:
            # Some gateways disable /models — fall through to a live call.
            pass

        if self._provider.supports_embeddings and self._provider.embedding_model:
            await self.embed(["ping"], model=self._provider.embedding_model)
            return True

        if self._provider.chat_model:
            result = await self.chat(
                [ChatMessage(role="user", content="ping")],
                model=self._provider.chat_model,
                max_tokens=8,
                temperature=0.0,
            )
            return bool(result.content)

        raise AIProviderError(
            "Provider has no chat or embedding model configured for testing."
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None
