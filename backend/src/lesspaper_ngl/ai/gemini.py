"""Google Gemini generateContent and embedContent adapters."""

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

    return str(payload)


class GeminiAdapter(AIProviderAdapter):
    """Async adapter for Gemini REST APIs."""

    def __init__(
        self,
        provider: AIProvider,
        api_key: str | None = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise AIProviderError("Gemini provider requires an API key.")

        self._provider = provider
        self._api_key = api_key
        self._base_url = _normalize_base_url(provider.base_url)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Content-Type": "application/json"},
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
            raise AIProviderError("No chat model configured for Gemini provider.")
        return resolved

    def _resolve_embedding_model(self, model: str | None) -> str:
        resolved = model or self._provider.embedding_model
        if not resolved:
            raise AIProviderError("No embedding model configured for Gemini provider.")
        return resolved

    def _model_path(self, model: str, action: str) -> str:
        model_name = model.removeprefix("models/")
        return f"/models/{model_name}:{action}"

    def _build_contents(self, messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        for message in messages:
            if message.role == "system":
                system_parts.append(message.content)
                continue

            role = "model" if message.role == "assistant" else "user"
            contents.append(
                {
                    "role": role,
                    "parts": [{"text": message.content}],
                }
            )

        if not contents:
            raise AIProviderError("At least one non-system message is required.")

        system_instruction = "\n\n".join(system_parts) if system_parts else None
        return system_instruction, contents

    async def _request(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        params = {"key": self._api_key}
        try:
            response = await self._client.post(
                path,
                params=params,
                json=payload,
                timeout=httpx.Timeout(timeout) if timeout is not None else None,
            )
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
            raise AIProviderError("Gemini returned invalid JSON.") from exc

        if not isinstance(data, dict):
            raise AIProviderError("Gemini returned an unexpected response payload.")
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
        system_instruction, contents = self._build_contents(messages)

        generation_config: dict[str, Any] = {"temperature": temperature}
        token_limit = max_tokens or self._provider.max_output_tokens
        if token_limit is not None:
            generation_config["maxOutputTokens"] = token_limit

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        data = await self._request(self._model_path(resolved_model, "generateContent"), payload)

        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise AIProviderError("Gemini response missing candidates.")

        first = candidates[0]
        if not isinstance(first, dict):
            raise AIProviderError("Gemini candidate has invalid shape.")

        content = first.get("content")
        if not isinstance(content, dict):
            raise AIProviderError("Gemini response missing content.")

        parts = content.get("parts")
        if not isinstance(parts, list):
            raise AIProviderError("Gemini response missing content parts.")

        text_parts: list[str] = []
        for part in parts:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)

        if not text_parts:
            raise AIProviderError("Gemini response did not include text content.")

        usage = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
        finish_reason = first.get("finishReason")
        finish_reason_str = finish_reason if isinstance(finish_reason, str) else None

        return ChatResult(
            content="\n".join(text_parts),
            model=resolved_model,
            input_tokens=_coerce_int(usage.get("promptTokenCount")),
            output_tokens=_coerce_int(usage.get("candidatesTokenCount")),
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
        embeddings: list[list[float]] = []
        total_tokens = 0

        for text in texts:
            payload = {
                "content": {"parts": [{"text": text}]},
            }
            data = await self._request(
                self._model_path(resolved_model, "embedContent"),
                payload,
                timeout=60.0,
            )
            embedding = data.get("embedding")
            if not isinstance(embedding, dict):
                raise AIProviderError("Gemini embed response missing embedding object.")

            values = embedding.get("values")
            if not isinstance(values, list):
                raise AIProviderError("Gemini embed response missing values.")

            embeddings.append([float(value) for value in values])

            usage = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
            token_count = _coerce_int(usage.get("promptTokenCount"))
            if token_count is not None:
                total_tokens += token_count

        return EmbeddingResult(
            embeddings=embeddings,
            model=resolved_model,
            input_tokens=total_tokens or None,
            raw={"count": len(embeddings)},
        )

    async def test_connection(self) -> bool:
        if self._provider.supports_embeddings and self._provider.embedding_model:
            await self.embed(["ping"], model=self._provider.embedding_model)
            return True

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
