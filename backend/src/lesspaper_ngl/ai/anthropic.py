"""Anthropic messages API adapter."""

from __future__ import annotations

from typing import Any

import httpx

from lesspaper_ngl.ai.base import (
    AIProviderAdapter,
    AIProviderError,
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ModelCapabilities,
)
from lesspaper_ngl.models import AIProvider

ANTHROPIC_VERSION = "2023-06-01"


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message
        message = payload.get("message")
        if isinstance(message, str):
            return message

    return str(payload)


class AnthropicAdapter(AIProviderAdapter):
    """Async adapter for Anthropic /v1/messages."""

    def __init__(
        self,
        provider: AIProvider,
        api_key: str | None = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise AIProviderError("Anthropic provider requires an API key.")

        self._provider = provider
        self._api_key = api_key
        self._base_url = _normalize_base_url(provider.base_url)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
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
            supports_embeddings=False,
            supports_vision=self._provider.supports_vision,
            context_window=self._provider.context_window,
            max_output_tokens=self._provider.max_output_tokens,
        )

    def _resolve_chat_model(self, model: str | None) -> str:
        resolved = model or self._provider.chat_model
        if not resolved:
            raise AIProviderError("No chat model configured for Anthropic provider.")
        return resolved

    def _split_messages(self, messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, str]]]:
        system_parts: list[str] = []
        conversation: list[dict[str, str]] = []

        for message in messages:
            if message.role == "system":
                system_parts.append(message.content)
                continue
            role = "assistant" if message.role == "assistant" else "user"
            conversation.append({"role": role, "content": message.content})

        if not conversation:
            raise AIProviderError("At least one non-system message is required.")

        system_prompt = "\n\n".join(system_parts) if system_parts else None
        return system_prompt, conversation

    async def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError(f"Request to {self._provider.name} timed out.") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Network error contacting {self._provider.name}: {exc}") from exc

        if response.status_code >= 400:
            raise AIProviderError(
                _extract_error_message(response),
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise AIProviderError("Anthropic returned invalid JSON.") from exc

        if not isinstance(data, dict):
            raise AIProviderError("Anthropic returned an unexpected response payload.")
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
        system_prompt, conversation = self._split_messages(messages)

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": conversation,
            "max_tokens": max_tokens or self._provider.max_output_tokens or 1024,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        data = await self._request("/v1/messages", payload)

        content_blocks = data.get("content")
        if not isinstance(content_blocks, list):
            raise AIProviderError("Anthropic response missing content blocks.")

        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)

        if not text_parts:
            raise AIProviderError("Anthropic response did not include text content.")

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        stop_reason = data.get("stop_reason")
        stop_reason_str = stop_reason if isinstance(stop_reason, str) else None

        return ChatResult(
            content="\n".join(text_parts),
            model=str(data.get("model", resolved_model)),
            input_tokens=_coerce_int(usage.get("input_tokens")),
            output_tokens=_coerce_int(usage.get("output_tokens")),
            finish_reason=stop_reason_str,
            raw=data,
        )

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        raise AIProviderError("Anthropic adapter does not support embeddings.")

    async def test_connection(self) -> bool:
        result = await self.chat(
            [ChatMessage(role="user", content="ping")],
            model=self._provider.chat_model,
            max_tokens=8,
            temperature=0.0,
        )
        return bool(result.content)

    async def aclose(self) -> None:
        await self._client.aclose()


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None
