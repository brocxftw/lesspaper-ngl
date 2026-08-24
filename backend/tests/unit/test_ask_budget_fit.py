"""Tests for hard Ask evidence budget fitting."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from lesspaper_ngl.ai.rag import RetrievedChunk, _fit_chunks_to_budget


def _chunk(text: str, token_count: int) -> RetrievedChunk:
    chunk = SimpleNamespace(
        id=uuid.uuid4(),
        text=text,
        token_count=token_count,
        page_number=1,
    )
    return RetrievedChunk(
        chunk=chunk,  # type: ignore[arg-type]
        document_id=uuid.uuid4(),
        document_title="Doc",
        score=1.0,
        source="keyword",
    )


def test_fit_chunks_skips_first_chunk_when_over_budget() -> None:
    ranked = [_chunk("huge " * 100, token_count=500)]
    selected = _fit_chunks_to_budget(ranked, max_chunks=3, token_budget=50)
    assert selected == []


def test_fit_chunks_admits_until_budget_exhausted() -> None:
    ranked = [
        _chunk("one", token_count=10),
        _chunk("two", token_count=10),
        _chunk("three", token_count=10),
    ]
    # Overhead for labels is non-zero; generous budget admits all three.
    selected = _fit_chunks_to_budget(ranked, max_chunks=3, token_budget=500)
    assert len(selected) == 3

    tight = _fit_chunks_to_budget(ranked, max_chunks=3, token_budget=80)
    assert 1 <= len(tight) <= 2
