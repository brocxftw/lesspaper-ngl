"""Structure-aware, token-safe document chunking."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

try:
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - optional dependency path
    _ENCODER = None

CHUNKING_VERSION = "v2-token-safe"
SECTION_MAX_LENGTH = 512

# Defaults used when no provider capability override is supplied.
TARGET_MIN_TOKENS = 400
TARGET_MAX_TOKENS = 512
MAX_TOKENS = 512
MIN_TOKENS = 100
OVERLAP_TOKENS = 64
OVERLAP_RATIO = 0.10  # fallback when overlap_tokens not used for block tails

HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|[A-Z0-9][A-Z0-9\s\-]{2,60}$|\d+(?:\.\d+)*[\.)]\s+.+)$"
)
# Backwards-compatible alias for internal callers.
_HEADING_RE = HEADING_RE


@dataclass(frozen=True)
class PageInput:
    page_number: int
    text: str


@dataclass(frozen=True)
class ChunkDraft:
    page_number: int | None
    page_end: int | None
    section: str | None
    text: str
    token_count: int
    chunk_index: int
    content_hash: str
    chunking_version: str = CHUNKING_VERSION


@dataclass(frozen=True)
class ChunkingLimits:
    target_min_tokens: int = TARGET_MIN_TOKENS
    target_max_tokens: int = TARGET_MAX_TOKENS
    max_tokens: int = MAX_TOKENS
    min_tokens: int = MIN_TOKENS
    overlap_tokens: int = OVERLAP_TOKENS


def estimate_tokens(text: str) -> int:
    """Estimate token count using tiktoken when available."""
    stripped = text.strip()
    if not stripped:
        return 0
    if _ENCODER is not None:
        return len(_ENCODER.encode(stripped))
    words = len(stripped.split())
    return max(1, int(words * 1.3))


def content_hash(text: str) -> str:
    """SHA-256 of normalised chunk text (stripped, NFC-ish via encode)."""
    normalised = " ".join(text.split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _truncate_section(section: str | None) -> str | None:
    if section is None:
        return None
    trimmed = section.strip()
    if not trimmed:
        return None
    if len(trimmed) <= SECTION_MAX_LENGTH:
        return trimmed
    return trimmed[:SECTION_MAX_LENGTH]


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # DOCX table rows are pipe-separated cells; not section headings.
    if stripped.count(" | ") >= 2:
        return False
    return bool(_HEADING_RE.match(stripped))


def chunk_pages(
    pages: list[PageInput | dict[str, object]],
    *,
    limits: ChunkingLimits | None = None,
) -> list[ChunkDraft]:
    """Split extracted pages into structure-aware, token-safe chunks."""
    cfg = limits or ChunkingLimits()
    normalized = [_coerce_page(page) for page in pages]
    blocks: list[_Block] = []
    for page in normalized:
        blocks.extend(_split_page_blocks(page.page_number, page.text, cfg.max_tokens))

    if not blocks:
        return []

    chunks: list[ChunkDraft] = []
    current: list[_Block] = []
    current_tokens = 0
    current_section: str | None = None
    chunk_index = 0

    def flush() -> None:
        nonlocal chunk_index, current, current_tokens, current_section
        if not current:
            return
        text = "\n\n".join(block.text for block in current).strip()
        if not text:
            current = []
            current_tokens = 0
            return

        page_start = current[0].page_number
        page_end = current[-1].page_number
        token_count = estimate_tokens(text)

        # Hard guard: split again if the joined chunk somehow exceeds max.
        if token_count > cfg.max_tokens:
            for part in _split_text_by_tokens(text, cfg.max_tokens):
                part_tokens = estimate_tokens(part)
                chunks.append(
                    ChunkDraft(
                        page_number=page_start,
                        page_end=page_end,
                        section=_truncate_section(current_section),
                        text=part,
                        token_count=part_tokens,
                        chunk_index=chunk_index,
                        content_hash=content_hash(part),
                    )
                )
                chunk_index += 1
            overlap_blocks = _overlap_tail(current, cfg.overlap_tokens)
            current = overlap_blocks
            current_tokens = sum(block.tokens for block in current)
            return

        chunks.append(
            ChunkDraft(
                page_number=page_start,
                page_end=page_end,
                section=_truncate_section(current_section),
                text=text,
                token_count=token_count,
                chunk_index=chunk_index,
                content_hash=content_hash(text),
            )
        )
        chunk_index += 1
        overlap_blocks = _overlap_tail(current, cfg.overlap_tokens)
        current = overlap_blocks
        current_tokens = sum(block.tokens for block in current)

    for block in blocks:
        if block.is_heading:
            if current and current_tokens >= cfg.min_tokens:
                flush()
            current_section = _truncate_section(block.text.strip("# ").strip())
            if current and current[-1].page_number != block.page_number:
                flush()

        prospective = current_tokens + block.tokens
        if current and prospective > cfg.max_tokens:
            flush()

        # Block itself may still exceed max after flush — split it.
        if block.tokens > cfg.max_tokens:
            if current:
                flush()
            for part in _split_text_by_tokens(block.text, cfg.max_tokens):
                part_tokens = estimate_tokens(part)
                chunks.append(
                    ChunkDraft(
                        page_number=block.page_number,
                        page_end=block.page_number,
                        section=_truncate_section(current_section),
                        text=part,
                        token_count=part_tokens,
                        chunk_index=chunk_index,
                        content_hash=content_hash(part),
                    )
                )
                chunk_index += 1
            current = []
            current_tokens = 0
            continue

        current.append(block)
        current_tokens += block.tokens

        if current_tokens >= cfg.target_max_tokens or current_tokens >= cfg.target_min_tokens and block.is_heading:
            flush()

    if current:
        if chunks and current_tokens < cfg.min_tokens:
            merged_text = f"{chunks[-1].text}\n\n" + "\n\n".join(b.text for b in current)
            merged_tokens = estimate_tokens(merged_text)
            if merged_tokens <= cfg.max_tokens:
                page_end = current[-1].page_number
                chunks[-1] = ChunkDraft(
                    page_number=chunks[-1].page_number,
                    page_end=page_end,
                    section=_truncate_section(chunks[-1].section or current_section),
                    text=merged_text.strip(),
                    token_count=merged_tokens,
                    chunk_index=chunks[-1].chunk_index,
                    content_hash=content_hash(merged_text),
                )
            else:
                flush()
        else:
            flush()

    return chunks


def split_oversized_text(
    text: str,
    *,
    max_tokens: int,
    page_number: int | None = None,
    page_end: int | None = None,
    section: str | None = None,
    start_index: int = 0,
) -> list[ChunkDraft]:
    """Split a single oversized chunk into token-safe drafts."""
    parts = _split_text_by_tokens(text, max_tokens)
    drafts: list[ChunkDraft] = []
    for offset, part in enumerate(parts):
        drafts.append(
            ChunkDraft(
                page_number=page_number,
                page_end=page_end if page_end is not None else page_number,
                section=_truncate_section(section),
                text=part,
                token_count=estimate_tokens(part),
                chunk_index=start_index + offset,
                content_hash=content_hash(part),
            )
        )
    return drafts


@dataclass
class _Block:
    page_number: int
    text: str
    tokens: int
    is_heading: bool = False


def _coerce_page(page: PageInput | dict[str, object]) -> PageInput:
    if isinstance(page, PageInput):
        return page
    page_number = int(page["page_number"])
    text = str(page["text"])
    return PageInput(page_number=page_number, text=text)


def _split_page_blocks(page_number: int, text: str, max_tokens: int) -> list[_Block]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return []
    blocks: list[_Block] = []
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue
        if len(lines) == 1:
            is_heading = _is_heading_line(lines[0])
            blocks.extend(
                _blocks_from_text(page_number, lines[0], is_heading=is_heading, max_tokens=max_tokens)
            )
            continue
        for line in lines:
            is_heading = _is_heading_line(line)
            blocks.extend(
                _blocks_from_text(page_number, line, is_heading=is_heading, max_tokens=max_tokens)
            )
    return blocks


def _blocks_from_text(
    page_number: int,
    text: str,
    *,
    is_heading: bool,
    max_tokens: int,
) -> list[_Block]:
    tokens = estimate_tokens(text)
    if tokens <= max_tokens:
        return [
            _Block(
                page_number=page_number,
                text=text,
                tokens=tokens,
                is_heading=is_heading,
            )
        ]
    # Headings that are somehow huge still get split; only first part keeps heading flag.
    parts = _split_text_by_tokens(text, max_tokens)
    result: list[_Block] = []
    for index, part in enumerate(parts):
        result.append(
            _Block(
                page_number=page_number,
                text=part,
                tokens=estimate_tokens(part),
                is_heading=is_heading and index == 0,
            )
        )
    return result


def _split_text_by_tokens(text: str, max_tokens: int) -> list[str]:
    """Split text into pieces each <= max_tokens (estimated)."""
    stripped = text.strip()
    if not stripped:
        return []
    if estimate_tokens(stripped) <= max_tokens:
        return [stripped]

    if _ENCODER is not None:
        token_ids = _ENCODER.encode(stripped)
        parts: list[str] = []
        for start in range(0, len(token_ids), max_tokens):
            piece = _ENCODER.decode(token_ids[start : start + max_tokens]).strip()
            if piece:
                parts.append(piece)
        return parts or [stripped]

    # Fallback: approximate by words (~1.3 tokens/word → words ≈ tokens/1.3)
    words = stripped.split()
    words_per_chunk = max(1, int(max_tokens / 1.3))
    parts = []
    for start in range(0, len(words), words_per_chunk):
        piece = " ".join(words[start : start + words_per_chunk]).strip()
        if piece:
            parts.append(piece)
    # Recursively harden if estimate still overshoots.
    hardened: list[str] = []
    for part in parts:
        if estimate_tokens(part) <= max_tokens:
            hardened.append(part)
        else:
            # Character window last resort.
            step = max(64, len(part) * max_tokens // max(estimate_tokens(part), 1))
            for i in range(0, len(part), step):
                slice_ = part[i : i + step].strip()
                if slice_:
                    hardened.append(slice_)
    return hardened or [stripped]


def _overlap_tail(blocks: list[_Block], overlap_tokens: int) -> list[_Block]:
    if not blocks:
        return []
    target = max(1, overlap_tokens)
    tail: list[_Block] = []
    running = 0
    for block in reversed(blocks):
        tail.insert(0, block)
        running += block.tokens
        if running >= target:
            break
    return tail
