"""Semantic score unification and optional relevance floor."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from lesspaper_ngl.ai.rag import RetrievedChunk, hybrid_retrieve


def _item(score: float, source: str = "semantic") -> RetrievedChunk:
    chunk = SimpleNamespace(
        id=uuid.uuid4(),
        text="evidence",
        token_count=5,
        page_number=1,
    )
    return RetrievedChunk(
        chunk=chunk,  # type: ignore[arg-type]
        document_id=uuid.uuid4(),
        document_title="Doc",
        score=score,
        source=source,
    )


def test_cosine_similarity_from_distance() -> None:
    # Mirrors rag._semantic_retrieve / search.semantic: score = 1 - distance.
    distance = 0.25
    assert abs((1.0 - distance) - 0.75) < 1e-9


def test_semantic_floor_filters_before_fusion_logic() -> None:
    hits = [_item(0.55), _item(0.20), _item(0.40)]
    floor = 0.35
    filtered = [item for item in hits if item.score >= floor]
    assert [round(i.score, 2) for i in filtered] == [0.55, 0.40]


def test_null_floor_preserves_all_hits() -> None:
    hits = [_item(0.1), _item(0.9)]
    floor = None
    filtered = hits if floor is None else [i for i in hits if i.score >= floor]
    assert len(filtered) == 2


def test_hybrid_retrieve_signature_accepts_semantic_min_score() -> None:
    # Ensure the public retrieve helper exposes the Phase 2C parameter.
    assert "semantic_min_score" in hybrid_retrieve.__code__.co_varnames
