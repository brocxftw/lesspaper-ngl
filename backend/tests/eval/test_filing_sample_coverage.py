"""Phase 1 AI eval scaffold: filing sample coverage on golden fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lesspaper_ngl.ai.filing_context import PageText, build_filing_sample
from lesspaper_ngl.services.chunking import estimate_tokens

FIXTURES = Path(__file__).parent / "fixtures" / "golden_documents.json"


def _load_docs() -> list[dict]:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return list(payload["documents"])


def _pages_for(doc: dict) -> list[PageText]:
    if doc.get("generated_pages"):
        n = int(doc["generated_pages"])
        pages: list[PageText] = []
        for i in range(1, n + 1):
            marker = f"UNIQUE_MANUAL_P{i:02d}"
            filler = " ".join(f"term{j}" for j in range(120))
            pages.append(PageText(i, f"Chapter {i}\n{marker}\n{filler}"))
        return pages
    return [PageText(int(p["page_number"]), str(p["text"])) for p in doc.get("pages", [])]


@pytest.mark.parametrize("doc", _load_docs(), ids=lambda d: d["id"])
def test_filing_sample_covers_expected_markers(doc: dict) -> None:
    pages = _pages_for(doc)
    full = "\n\n".join(p.text for p in pages)
    sample = build_filing_sample(
        filename=doc["filename"],
        pages=pages,
        extracted_text=full,
        page_count=len(pages),
    )

    if doc.get("expect_full_text"):
        assert sample.used_full_text is True
        assert sample.document_text == full.strip()
    else:
        # Long synthetic docs must stay within the filing budget.
        if estimate_tokens(full) > 2500:
            assert sample.used_full_text is False
            assert estimate_tokens(sample.document_text) <= 2550

    for marker in doc["expect_sample_markers"]:
        assert marker in sample.document_text or marker in sample.signals_block, marker

    # Prefix truncation regression: ending markers must survive for long docs.
    if not doc.get("expect_full_text") and estimate_tokens(full) > 2500:
        ending = doc["expect_sample_markers"][-1]
        prefix = full[:10_000]
        # If the marker is beyond the old 10k char window, sampling must still include it.
        if ending not in prefix:
            assert ending in sample.document_text


def test_prefix_truncation_misses_manual_ending_but_sample_keeps_it() -> None:
    doc = next(d for d in _load_docs() if d["id"] == "book-excerpt-01")
    pages = _pages_for(doc)
    full = "\n\n".join(p.text for p in pages)
    assert "UNIQUE_MANUAL_P40" not in full[:10_000]
    sample = build_filing_sample(
        filename=doc["filename"],
        pages=pages,
        extracted_text=full,
        page_count=len(pages),
    )
    assert "UNIQUE_MANUAL_P40" in sample.document_text
    assert "UNIQUE_MANUAL_P01" in sample.document_text


# --- Metric stubs for future live evaluation ---------------------------------


def filing_suggestion_metrics_stub() -> dict[str, float | None]:
    """Placeholder metric keys for live filing eval."""
    return {
        "title_usefulness": None,
        "folder_correct": None,
        "tags_correct": None,
        "document_type_correct": None,
        "correspondent_correct": None,
        "malformed_output_rate": None,
        "latency_ms": None,
        "input_tokens": None,
        "output_tokens": None,
    }


def retrieval_metrics_stub() -> dict[str, float | None]:
    return {
        "recall_at_k": None,
        "precision_at_k": None,
        "relevant_chunk_rank": None,
        "irrelevant_chunk_rate": None,
    }


def ask_metrics_stub() -> dict[str, float | None]:
    return {
        "evidence_correctness": None,
        "citation_correctness": None,
        "hallucination_rate": None,
        "insufficient_evidence_precision": None,
        "insufficient_evidence_recall": None,
        "answer_usefulness": None,
        "latency_ms": None,
        "context_tokens": None,
        "output_tokens": None,
    }


def test_metric_stubs_expose_expected_keys() -> None:
    assert "malformed_output_rate" in filing_suggestion_metrics_stub()
    assert "recall_at_k" in retrieval_metrics_stub()
    assert "citation_correctness" in ask_metrics_stub()
