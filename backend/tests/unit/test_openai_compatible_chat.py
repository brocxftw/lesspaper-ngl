"""Unit tests for OpenAI-compatible chat content extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from lesspaper_ngl.ai.base import AIProviderError, ChatMessage
from lesspaper_ngl.ai.openai_compatible import OpenAICompatibleAdapter


def _adapter() -> OpenAICompatibleAdapter:
    provider = MagicMock()
    provider.name = "test-provider"
    provider.base_url = "http://localhost:1234/v1"
    provider.chat_model = "test-model"
    provider.embedding_model = None
    provider.max_output_tokens = 2048
    provider.supports_embeddings = False
    provider.supports_vision = False
    provider.context_window = 8192
    provider.is_local = False
    return OpenAICompatibleAdapter(provider, api_key=None)


@pytest.mark.asyncio
async def test_chat_falls_back_to_reasoning_content_when_finished() -> None:
    adapter = _adapter()
    adapter._request = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "model": "test-model",
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning_content": '{"folder_path":"Finance","tags":["a"]}',
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }
    )
    result = await adapter.chat([ChatMessage(role="user", content="hi")])
    assert "Finance" in result.content


@pytest.mark.asyncio
async def test_chat_preserves_provider_reported_cost() -> None:
    adapter = _adapter()
    adapter._request = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "model": "test-model",
            "choices": [{"message": {"content": "Done"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "cost": 0.00042},
        }
    )

    result = await adapter.chat([ChatMessage(role="user", content="hi")])

    assert result.reported_cost == pytest.approx(0.00042)
    assert result.cost_currency == "USD"


@pytest.mark.asyncio
async def test_chat_raises_when_truncated_with_empty_content() -> None:
    """Thinking models that exhaust max_tokens mid-reason must not silently succeed."""
    adapter = _adapter()
    adapter._request = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "model": "test-model",
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning_content": "Still thinking about folders…",
                    },
                    "finish_reason": "length",
                }
            ],
            "usage": {"completion_tokens": 2048},
        }
    )
    with pytest.raises(AIProviderError, match="truncated before producing content"):
        await adapter.chat([ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_chat_raises_when_content_and_reasoning_empty() -> None:
    adapter = _adapter()
    adapter._request = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "model": "test-model",
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
            "usage": {},
        }
    )
    with pytest.raises(AIProviderError, match="missing content"):
        await adapter.chat([ChatMessage(role="user", content="hi")])
