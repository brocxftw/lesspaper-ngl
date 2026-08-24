"""Unit tests for deterministic filing-context sampling."""

from __future__ import annotations

from lesspaper_ngl.ai.filing_context import (
    FILING_TEXT_TOKEN_BUDGET,
    PageText,
    build_filing_sample,
    format_filing_document_block,
    legacy_prefix_fallback,
    rank_folder_candidates,
    rank_tag_candidates,
    tokenize_for_candidates,
)
from lesspaper_ngl.services.chunking import estimate_tokens


def test_short_document_returns_full_text() -> None:
    text = "Invoice from ACME for January 2026.\nTotal due: 100."
    sample = build_filing_sample(
        filename="acme-invoice.pdf",
        pages=[PageText(1, text)],
        extracted_text=text,
        page_count=1,
    )
    assert sample.used_full_text is True
    assert sample.document_text == text
    assert "filename: acme-invoice.pdf" in sample.signals_block
    assert "page_count: 1" in sample.signals_block


def test_long_document_covers_beginning_and_ending() -> None:
    pages = []
    for i in range(1, 21):
        marker = f"UNIQUE_PAGE_{i:02d}_MARKER"
        body = " ".join([f"word{j}" for j in range(200)])
        pages.append(PageText(i, f"SECTION {i}\n{marker}\n{body}"))
    full = "\n\n".join(p.text for p in pages)
    assert estimate_tokens(full) > FILING_TEXT_TOKEN_BUDGET

    sample = build_filing_sample(
        filename="long-report.pdf",
        pages=pages,
        extracted_text=full,
        page_count=20,
    )
    assert sample.used_full_text is False
    assert "[BEGINNING]" in sample.document_text
    assert "[ENDING]" in sample.document_text
    assert "UNIQUE_PAGE_01_MARKER" in sample.document_text
    assert "UNIQUE_PAGE_20_MARKER" in sample.document_text
    # Middle content that prefix truncation would miss should appear when sampled.
    assert (
        "UNIQUE_PAGE_10_MARKER" in sample.document_text
        or "UNIQUE_PAGE_14_MARKER" in sample.document_text
    )
    assert estimate_tokens(sample.document_text) <= FILING_TEXT_TOKEN_BUDGET + 50


def test_missing_pages_falls_back_to_extracted_text() -> None:
    # Build long text without page rows.
    chunks = [f"PART_{i} " + ("lorem " * 80) for i in range(30)]
    text = "\n\n".join(chunks)
    sample = build_filing_sample(
        filename="blob.txt",
        pages=[],
        extracted_text=text,
        page_count=None,
    )
    assert sample.used_full_text is False
    assert "[BEGINNING]" in sample.document_text
    assert "PART_0" in sample.document_text


def test_sampling_is_deterministic() -> None:
    pages = [PageText(i, f"Heading {i}\n" + ("alpha beta gamma " * 100)) for i in range(1, 12)]
    full = "\n\n".join(p.text for p in pages)
    a = build_filing_sample(filename="x.pdf", pages=pages, extracted_text=full, page_count=11)
    b = build_filing_sample(filename="x.pdf", pages=pages, extracted_text=full, page_count=11)
    assert a.document_text == b.document_text
    assert a.signals_block == b.signals_block


def test_format_block_includes_signals_and_text() -> None:
    sample = build_filing_sample(
        filename="note.pdf",
        pages=[PageText(1, "Hello world")],
        extracted_text="Hello world",
        page_count=1,
    )
    block = format_filing_document_block(sample)
    assert "Detected signals:" in block
    assert "Document text:\nHello world" in block


def test_legacy_prefix_fallback() -> None:
    text = "a" * 20_000
    assert len(legacy_prefix_fallback(text)) == 10_000


def test_rank_folder_candidates_prefers_lexical_overlap() -> None:
    paths = [
        "Archive / Misc",
        "Finance / Insurance",
        "Identity / Passports",
        "Finance / Salary / 2025",
    ]
    tokens = tokenize_for_candidates("payslip salary january.pdf", "Monthly salary payment advice")
    ranked = rank_folder_candidates(
        paths,
        query_tokens=tokens,
        document_counts={"Archive / Misc": 50, "Finance / Salary / 2025": 2},
    )
    assert ranked[0].startswith("Finance")
    assert len(ranked) <= 20


def test_rank_folder_candidates_falls_back_to_short_paths() -> None:
    paths = ["Zzz / Long Name Here", "A / B", "Medium / Path"]
    ranked = rank_folder_candidates(paths, query_tokens=["zzzznotpresent"], document_counts={})
    assert ranked == sorted(paths, key=len)[:20]


def test_resume_filename_boosts_job_hunt_folder() -> None:
    paths = ["Finance / Salary / 2025", "Job Hunt", "ID / Documents"]
    tokens = tokenize_for_candidates(
        "Resume Kapt Abdul Azim - Senior Data Analyst.pdf",
        "Senior Data Analyst with experience in Azure SQL reporting",
    )
    ranked = rank_folder_candidates(
        paths,
        query_tokens=tokens,
        document_counts={"Finance / Salary / 2025": 1, "Job Hunt": 1},
        filename="Resume Kapt Abdul Azim - Senior Data Analyst.pdf",
    )
    assert ranked[0] == "Job Hunt"
    assert all("Salary" not in path for path in ranked)


def test_resume_filename_excludes_salary_even_without_job_folder() -> None:
    paths = ["Finance / Salary / 2026", "Finance / Insurance", "ID / Documents"]
    tokens = tokenize_for_candidates("Resume Jane Doe.pdf", "Software engineer")
    ranked = rank_folder_candidates(
        paths,
        query_tokens=tokens,
        document_counts={"Finance / Salary / 2026": 10},
        filename="Resume Jane Doe.pdf",
    )
    assert "Finance / Salary / 2026" not in ranked
    assert ranked  # still returns other folders


def test_rank_tag_candidates_prefers_overlap_then_usage() -> None:
    tags = [("finance", 1), ("family", 20), ("invoice", 3), ("travel", 8)]
    tokens = tokenize_for_candidates("acme invoice january")
    ranked = rank_tag_candidates(tags, query_tokens=tokens)
    assert ranked[0] == "invoice"
    assert "family" not in ranked  # no lexical overlap → excluded


def test_rank_tag_candidates_empty_when_no_overlap() -> None:
    tags = [("alpha", 1), ("beta", 9), ("gamma", 3)]
    ranked = rank_tag_candidates(tags, query_tokens=["nomatchtoken"])
    assert ranked == []


def test_filing_prompt_examples_are_neutral() -> None:
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "src/lesspaper_ngl/workers/processor.py"
    text = source.read_text(encoding="utf-8")
    assert "Finance / Salary / 2025" not in text
    assert "Topic / PersonOrOrg" in text
    assert "Category / Year" in text
    assert "never file them under Finance, Salary" in text

