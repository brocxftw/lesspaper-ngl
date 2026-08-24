"""Document chunking unit tests."""

from __future__ import annotations

from lesspaper_ngl.services.chunking import (
    MAX_TOKENS,
    MIN_TOKENS,
    TARGET_MAX_TOKENS,
    ChunkingLimits,
    PageInput,
    chunk_pages,
    content_hash,
    estimate_tokens,
    split_oversized_text,
)


def test_chunk_sizes_respect_bounds() -> None:
    paragraphs = []
    for i in range(40):
        paragraphs.append(
            f"Section {i}\n\n"
            + ("Word " * 120)
            + f"\n\nLPPSA refinance detail paragraph {i} with RM 420000 tenure 25 years."
        )
    long_text = "\n\n".join(paragraphs)
    pages = [PageInput(page_number=1, text=long_text)]

    chunks = chunk_pages(pages)
    assert len(chunks) > 1

    for chunk in chunks:
        assert chunk.token_count <= MAX_TOKENS
        assert chunk.text.strip()
        assert chunk.content_hash
        assert chunk.page_end is not None

    token_counts = [c.token_count for c in chunks]
    mid_chunks = token_counts[1:-1] if len(token_counts) > 2 else token_counts
    assert any(count >= MIN_TOKENS for count in mid_chunks) or len(chunks) == 1
    assert any(count <= TARGET_MAX_TOKENS + 100 for count in token_counts)


def test_empty_pages_produce_no_chunks() -> None:
    assert chunk_pages([PageInput(page_number=1, text="   ")]) == []


def test_estimate_tokens_nonzero_for_text() -> None:
    assert estimate_tokens("hello world") >= 1


def test_tiny_document_single_chunk() -> None:
    chunks = chunk_pages([PageInput(page_number=1, text="Short note.")])
    assert len(chunks) == 1
    assert chunks[0].page_number == 1
    assert chunks[0].page_end == 1


def test_unicode_and_overlap() -> None:
    text = ("Καλημέρα κόσμε. " * 80) + "\n\n" + ("こんにちは世界。 " * 80)
    chunks = chunk_pages(
        [PageInput(page_number=1, text=text)],
        limits=ChunkingLimits(max_tokens=64, target_max_tokens=64, target_min_tokens=32, min_tokens=8, overlap_tokens=8),
    )
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count <= 64


def test_long_unbroken_text_is_hard_split() -> None:
    # No paragraph breaks — must still stay under max tokens.
    text = "word " * 5000
    chunks = chunk_pages(
        [PageInput(page_number=3, text=text)],
        limits=ChunkingLimits(max_tokens=100, target_max_tokens=100, target_min_tokens=50, min_tokens=10, overlap_tokens=10),
    )
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= 100
        assert chunk.page_number == 3
        assert chunk.page_end == 3


def test_page_span_preserved() -> None:
    pages = [
        PageInput(page_number=1, text="Alpha " * 40),
        PageInput(page_number=2, text="Beta " * 40),
    ]
    chunks = chunk_pages(
        pages,
        limits=ChunkingLimits(max_tokens=200, target_max_tokens=200, target_min_tokens=20, min_tokens=5, overlap_tokens=5),
    )
    assert chunks
    assert any(c.page_end and c.page_end >= (c.page_number or 0) for c in chunks)


def test_docx_table_rows_do_not_produce_oversized_sections() -> None:
    """DOCX table extraction can emit long pipe-separated rows; sections must fit DB."""
    table_row = (
        "5. | Pengambilan | Pengambilan | Pengambilan | Pengambilan | Pengambilan | "
        "Pengambilan | : | : | : | GRADUAN (PEGAWAI KADET LUAR NEGARA) - TUGAS AM | "
        "GRADUAN (PEGAWAI KADET LUAR NEGARA) - TUGAS AM | GRADUAN (PEGAWAI KADET LUAR NEGARA) - TUGAS AM"
    )
    text = f"{table_row}\n\nSome body paragraph with enough words to form a chunk."
    chunks = chunk_pages([PageInput(page_number=1, text=text)])
    assert chunks
    for chunk in chunks:
        assert chunk.section is None or len(chunk.section) <= 512

    assert content_hash("hello   world") == content_hash("hello world")
    assert content_hash("a") != content_hash("b")


def test_split_oversized_text_helper() -> None:
    drafts = split_oversized_text("token " * 400, max_tokens=50, page_number=7, start_index=10)
    assert len(drafts) > 1
    assert drafts[0].chunk_index == 10
    assert drafts[1].chunk_index == 11
    for draft in drafts:
        assert draft.token_count <= 50
        assert draft.page_number == 7


def test_blank_document() -> None:
    assert chunk_pages([]) == []
    assert chunk_pages([PageInput(page_number=1, text=""), PageInput(page_number=2, text="\n\n")]) == []
