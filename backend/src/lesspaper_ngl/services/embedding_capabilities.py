"""Resolve embedding provider capability defaults."""

from __future__ import annotations

from dataclasses import dataclass

from lesspaper_ngl.models import AIProvider
from lesspaper_ngl.services.chunking import ChunkingLimits

DEFAULT_MAX_INPUT_TOKENS = 8192
DEFAULT_RECOMMENDED_CHUNK_TOKENS = 512
DEFAULT_CHUNK_OVERLAP_TOKENS = 64
DEFAULT_BATCH_SIZE = 16
DEFAULT_MAX_BATCH_SIZE = 32
DEFAULT_CONCURRENCY = 1

# Soft budgets for a single EMBEDDING job before continuation re-enqueue.
DEFAULT_JOB_BATCH_BUDGET = 64
DEFAULT_JOB_TIME_BUDGET_SECONDS = 300.0
MAX_ISOLATION_DEPTH = 5
MAX_CHUNK_EMBED_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class EmbeddingCapabilities:
    max_input_tokens: int
    recommended_chunk_tokens: int
    overlap_tokens: int
    batch_size: int
    max_batch_size: int
    concurrency: int
    job_batch_budget: int = DEFAULT_JOB_BATCH_BUDGET
    job_time_budget_seconds: float = DEFAULT_JOB_TIME_BUDGET_SECONDS

    def chunking_limits(self) -> ChunkingLimits:
        chunk = min(self.recommended_chunk_tokens, self.max_input_tokens)
        chunk = max(64, chunk)
        return ChunkingLimits(
            target_min_tokens=max(64, int(chunk * 0.75)),
            target_max_tokens=chunk,
            max_tokens=chunk,
            min_tokens=max(32, int(chunk * 0.2)),
            overlap_tokens=min(self.overlap_tokens, max(1, chunk // 4)),
        )


def resolve_embedding_capabilities(provider: AIProvider | None) -> EmbeddingCapabilities:
    """Build effective embedding limits from provider row (nullable → defaults)."""
    max_input = _positive(getattr(provider, "embedding_max_input_tokens", None), DEFAULT_MAX_INPUT_TOKENS)
    recommended = _positive(
        getattr(provider, "embedding_recommended_chunk_tokens", None),
        DEFAULT_RECOMMENDED_CHUNK_TOKENS,
    )
    recommended = min(recommended, max_input)

    max_batch = _positive(
        getattr(provider, "embedding_max_batch_size", None),
        DEFAULT_MAX_BATCH_SIZE,
    )
    batch = _positive(getattr(provider, "embedding_batch_size", None), DEFAULT_BATCH_SIZE)
    batch = min(batch, max_batch)
    batch = max(1, batch)

    concurrency = _positive(
        getattr(provider, "embedding_concurrency", None),
        DEFAULT_CONCURRENCY,
    )
    # Local providers default to serial embeds even if misconfigured high.
    if provider is not None and provider.is_local:
        concurrency = min(concurrency, 1)

    return EmbeddingCapabilities(
        max_input_tokens=max_input,
        recommended_chunk_tokens=recommended,
        overlap_tokens=DEFAULT_CHUNK_OVERLAP_TOKENS,
        batch_size=batch,
        max_batch_size=max_batch,
        concurrency=max(1, concurrency),
    )


def _positive(value: int | None, default: int) -> int:
    if value is None or value <= 0:
        return default
    return int(value)
