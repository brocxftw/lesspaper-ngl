"""Unit tests for bounded embedding pipeline helpers and behaviour."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from lesspaper_ngl.ai.base import AIProviderError, EmbeddingResult
from lesspaper_ngl.ai.retry import (
    is_non_retryable_ai_error,
    is_oversized_input_error,
    is_transient_ai_error,
)
from lesspaper_ngl.services.embedding_capabilities import (
    DEFAULT_BATCH_SIZE,
    resolve_embedding_capabilities,
)
from lesspaper_ngl.services.embedding_pipeline import iter_batches


def test_iter_batches_boundaries() -> None:
    assert iter_batches([], 16) == []
    assert iter_batches([1], 16) == [[1]]
    assert iter_batches(list(range(15)), 16) == [list(range(15))]
    assert iter_batches(list(range(16)), 16) == [list(range(16))]
    assert iter_batches(list(range(17)), 16) == [list(range(16)), [16]]
    big = list(range(1000))
    batches = iter_batches(big, 16)
    flat = [item for batch in batches for item in batch]
    assert flat == big
    assert all(len(batch) <= 16 for batch in batches)
    assert len(batches) == 63  # 62*16=992 + 8


def test_iter_batches_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        iter_batches([1], 0)


def test_resolve_embedding_capabilities_defaults() -> None:
    caps = resolve_embedding_capabilities(None)
    assert caps.batch_size == DEFAULT_BATCH_SIZE
    assert caps.concurrency == 1
    assert caps.max_input_tokens == 8192
    limits = caps.chunking_limits()
    assert limits.max_tokens == 512


def test_resolve_embedding_capabilities_from_provider() -> None:
    provider = SimpleNamespace(
        embedding_max_input_tokens=4096,
        embedding_recommended_chunk_tokens=256,
        embedding_batch_size=8,
        embedding_max_batch_size=16,
        embedding_concurrency=4,
        is_local=True,
    )
    caps = resolve_embedding_capabilities(provider)
    assert caps.batch_size == 8
    assert caps.recommended_chunk_tokens == 256
    assert caps.max_input_tokens == 4096
    # Local providers force concurrency 1.
    assert caps.concurrency == 1


def test_retry_classification() -> None:
    assert is_transient_ai_error(AIProviderError("timeout", status_code=504))
    assert is_transient_ai_error(AIProviderError("rate limited", status_code=429))
    assert is_oversized_input_error(AIProviderError("maximum context length exceeded", status_code=400))
    assert is_non_retryable_ai_error(AIProviderError("invalid api key", status_code=401))
    assert not is_transient_ai_error(AIProviderError("invalid api key", status_code=401))


@pytest.mark.asyncio
async def test_call_embed_retries_transient_then_succeeds() -> None:
    from lesspaper_ngl.services.embedding_pipeline import _call_embed_with_retries

    adapter = MagicMock()
    adapter.embed = AsyncMock(
        side_effect=[
            AIProviderError("timed out", status_code=504),
            EmbeddingResult(embeddings=[[0.1, 0.2]], model="m", input_tokens=3),
        ]
    )
    vectors, tokens, model = await _call_embed_with_retries(adapter, ["hi"], model="m")
    assert vectors == [[0.1, 0.2]]
    assert tokens == 3
    assert model == "m"
    assert adapter.embed.await_count == 2


@pytest.mark.asyncio
async def test_call_embed_does_not_retry_oversized() -> None:
    from lesspaper_ngl.services.embedding_pipeline import _call_embed_with_retries

    adapter = MagicMock()
    adapter.embed = AsyncMock(
        side_effect=AIProviderError("context length exceeded", status_code=400)
    )
    with pytest.raises(AIProviderError):
        await _call_embed_with_retries(adapter, ["huge"], model="m")
    assert adapter.embed.await_count == 1


@pytest.mark.asyncio
async def test_embed_batch_stores_requested_model_not_provider_echo() -> None:
    """OpenRouter-style providers may echo an unprefixed model name (#53)."""
    from lesspaper_ngl.models import ChunkEmbeddingStatus
    from lesspaper_ngl.services.embedding_capabilities import resolve_embedding_capabilities
    from lesspaper_ngl.services.embedding_pipeline import _embed_batch_with_isolation

    requested = "openai/text-embedding-3-small"
    echoed = "text-embedding-3-small"
    chunk = SimpleNamespace(
        id="chunk-1",
        text="hello",
        embedding=None,
        embedding_provider=None,
        embedding_model=None,
        embedding_dimension=None,
        embedding_status=ChunkEmbeddingStatus.PENDING,
        embedding_error=None,
        embedding_attempts=0,
    )
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    adapter = MagicMock()
    adapter.embed = AsyncMock(
        return_value=EmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3]],
            model=echoed,
            input_tokens=2,
        )
    )
    caps = resolve_embedding_capabilities(None)

    outcome = await _embed_batch_with_isolation(
        session,
        doc=SimpleNamespace(id="doc-1"),
        chunks=[chunk],
        adapter=adapter,
        provider_name="openrouter",
        model=requested,
        caps=caps,
        depth=0,
    )

    assert outcome.embedded == 1
    assert chunk.embedding_model == requested
    assert chunk.embedding_model != echoed
    assert chunk.embedding_provider == "openrouter"
    assert chunk.embedding_status == ChunkEmbeddingStatus.EMBEDDED
