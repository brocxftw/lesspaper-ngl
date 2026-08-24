"""AI provider adapter factory."""

from __future__ import annotations

from lesspaper_ngl.ai.anthropic import AnthropicAdapter
from lesspaper_ngl.ai.base import AIProviderAdapter
from lesspaper_ngl.ai.gemini import GeminiAdapter
from lesspaper_ngl.ai.openai_compatible import OpenAICompatibleAdapter
from lesspaper_ngl.core.security import decrypt_secret
from lesspaper_ngl.models import AIProvider, ProviderKind


def get_adapter(
    provider: AIProvider,
    api_key: str | None = None,
    *,
    timeout: float = 120.0,
) -> AIProviderAdapter:
    """Return the adapter implementation for a configured provider."""
    resolved_key = api_key
    if resolved_key is None and provider.encrypted_api_key:
        resolved_key = decrypt_secret(provider.encrypted_api_key)

    match provider.kind:
        case (
            ProviderKind.OPENAI_COMPATIBLE
            | ProviderKind.OPENAI
            | ProviderKind.OPENROUTER
            | ProviderKind.OLLAMA
        ):
            return OpenAICompatibleAdapter(provider, resolved_key, timeout=timeout)
        case ProviderKind.ANTHROPIC:
            return AnthropicAdapter(provider, resolved_key, timeout=timeout)
        case ProviderKind.GEMINI:
            return GeminiAdapter(provider, resolved_key, timeout=timeout)
        case _:
            raise ValueError(f"Unsupported provider kind: {provider.kind}")
