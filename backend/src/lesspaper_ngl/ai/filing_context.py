"""Deterministic filing-context preparation (no LLM calls).

Builds a bounded, representative document sample and lexical folder/tag
candidates so small instruct models see useful context without oversized prompts.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from lesspaper_ngl.services.chunking import HEADING_RE, estimate_tokens

# Roughly equivalent to the former ~10_000 character prefix.
FILING_TEXT_TOKEN_BUDGET = 2500

# Lexical candidate limits (Phase 2).
FILING_FOLDER_CANDIDATE_LIMIT = 20
FILING_TAG_CANDIDATE_LIMIT = 20

_LEGACY_CHAR_FALLBACK = 10_000

_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})\b",
    re.IGNORECASE,
)
_ORG_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9][A-Z0-9&.-]{1,40}\b")
_WORD_RE = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "had",
        "her",
        "was",
        "one",
        "our",
        "out",
        "day",
        "get",
        "has",
        "him",
        "his",
        "how",
        "man",
        "new",
        "now",
        "old",
        "see",
        "two",
        "way",
        "who",
        "boy",
        "did",
        "its",
        "let",
        "put",
        "say",
        "she",
        "too",
        "use",
        "this",
        "that",
        "with",
        "from",
        "have",
        "been",
        "were",
        "they",
        "will",
        "each",
        "make",
        "like",
        "long",
        "look",
        "many",
        "some",
        "than",
        "them",
        "then",
        "these",
        "what",
        "when",
        "your",
        "which",
        "their",
        "there",
        "would",
        "about",
        "could",
        "other",
        "into",
        "over",
        "such",
        "page",
        "document",
        "www",
        "http",
        "https",
        "com",
        "pdf",
    }
)


@dataclass(frozen=True, slots=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class FilingSample:
    """Representative document sample for metadata suggestion prompts."""

    document_text: str
    signals_block: str
    token_count: int
    used_full_text: bool


def build_filing_sample(
    *,
    filename: str,
    pages: list[PageText] | None,
    extracted_text: str,
    page_count: int | None = None,
    token_budget: int = FILING_TEXT_TOKEN_BUDGET,
) -> FilingSample:
    """Build a token-bounded representative sample of document text.

    Prefers ordered page texts; falls back to extracted_text windows.
    Short documents are returned in full. On unexpected failure callers
    should fall back to ``extracted_text[:10000]``.
    """
    cleaned = (extracted_text or "").strip()
    page_rows = _normalise_pages(pages, cleaned)
    full = "\n\n".join(p.text for p in page_rows if p.text).strip() or cleaned
    if not full:
        return FilingSample(document_text="", signals_block="", token_count=0, used_full_text=True)

    full_tokens = estimate_tokens(full)
    if full_tokens <= token_budget:
        signals = _build_signals(
            filename=filename,
            page_count=page_count or len(page_rows) or None,
            text=full,
        )
        return FilingSample(
            document_text=full,
            signals_block=signals,
            token_count=full_tokens,
            used_full_text=True,
        )

    sampled = _sample_windows(page_rows if page_rows else [PageText(1, full)], token_budget)
    signals = _build_signals(
        filename=filename,
        page_count=page_count or (len(page_rows) if page_rows else None),
        text=full,
    )
    return FilingSample(
        document_text=sampled,
        signals_block=signals,
        token_count=estimate_tokens(sampled),
        used_full_text=False,
    )


def legacy_prefix_fallback(extracted_text: str) -> str:
    """Former filing truncation used when sampling fails."""
    return (extracted_text or "")[:_LEGACY_CHAR_FALLBACK]


def tokenize_for_candidates(*parts: str) -> list[str]:
    """Lowercased content tokens for lexical folder/tag ranking."""
    blob = " ".join(p for p in parts if p)
    counts: Counter[str] = Counter()
    for match in _WORD_RE.finditer(blob):
        token = match.group(0).lower()
        if token in _STOPWORDS or token.isdigit():
            continue
        counts[token] += 1
    # Prefer informative terms; keep stable order by (-freq, token).
    return [tok for tok, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


_RESUME_FILENAME_HINTS = ("resume", "cv", "curriculum")
_JOB_FOLDER_TOKENS = frozenset(
    {"job", "jobs", "career", "careers", "resume", "resumes", "hunt", "cv"}
)
_SALARY_FOLDER_TOKENS = frozenset(
    {"salary", "salaries", "payslip", "payslips", "payroll", "wage", "wages"}
)


def rank_folder_candidates(
    folder_paths: list[str],
    *,
    query_tokens: list[str],
    document_counts: dict[str, int] | None = None,
    limit: int = FILING_FOLDER_CANDIDATE_LIMIT,
    filename: str | None = None,
) -> list[str]:
    """Rank folder paths by lexical overlap with query tokens + doc-count boost.

    Resume/CV filenames:
    - boost Job Hunt / career-like paths
    - exclude Finance/Salary/payroll-like paths from the candidate list entirely
      (small models otherwise latch onto those existing folders).
    """
    if not folder_paths:
        return []
    if limit <= 0:
        return []

    resume_like = _filename_looks_like_resume(filename)
    paths = list(folder_paths)
    if resume_like:
        filtered = [p for p in paths if not _path_looks_like_salary_folder(p)]
        # Keep at least something to choose from if filtering removed everything.
        paths = filtered or paths

    counts = document_counts or {}
    query_set = set(query_tokens[:80])
    scored: list[tuple[float, int, str]] = []
    for path in paths:
        path_tokens = set(tokenize_for_candidates(path.replace("/", " ")))
        overlap = len(query_set & path_tokens)
        boost = float(counts.get(path, 0))
        score = (overlap * 100.0) + (boost * 0.1) - (len(path) * 0.001)
        if resume_like and _path_looks_like_job_folder(path):
            score += 50.0
        scored.append((score, -len(path), path))

    scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    if scored and scored[0][0] <= 0:
        return sorted(paths, key=len)[:limit]
    return [path for _, _, path in scored[:limit]]


def rank_tag_candidates(
    tags: list[tuple[str, int]],
    *,
    query_tokens: list[str],
    limit: int = FILING_TAG_CANDIDATE_LIMIT,
) -> list[str]:
    """Rank ``(tag_name, usage_count)`` by lexical overlap.

    Returns only tags with at least one overlapping token. When nothing overlaps,
    returns an empty list so the model invents topical tags instead of dumping
    popular unrelated catalogue entries.
    """
    if not tags:
        return []
    if limit <= 0:
        return []

    query_set = set(query_tokens[:80])
    scored: list[tuple[float, int, str]] = []
    for name, usage in tags:
        name_tokens = set(tokenize_for_candidates(name))
        overlap = len(query_set & name_tokens)
        if overlap <= 0:
            continue
        score = (overlap * 100.0) + float(max(0, usage))
        scored.append((score, usage, name))

    scored.sort(key=lambda row: (-row[0], -row[1], row[2].lower()))
    return [name for _, _, name in scored[:limit]]


def _filename_looks_like_resume(filename: str | None) -> bool:
    if not filename:
        return False
    lowered = filename.lower()
    return any(token in lowered for token in _RESUME_FILENAME_HINTS)


def _path_looks_like_job_folder(path: str) -> bool:
    tokens = set(tokenize_for_candidates(path.replace("/", " ")))
    return bool(tokens & _JOB_FOLDER_TOKENS)


def _path_looks_like_salary_folder(path: str) -> bool:
    tokens = set(tokenize_for_candidates(path.replace("/", " ")))
    if tokens & _SALARY_FOLDER_TOKENS:
        return True
    # "Finance / Salary / …" and bare "Salary" segments.
    lowered = path.lower()
    return "salary" in lowered or "payslip" in lowered or "payroll" in lowered


def format_filing_document_block(sample: FilingSample) -> str:
    """Render sample + signals for the filing prompt."""
    parts: list[str] = []
    if sample.signals_block.strip():
        parts.append(sample.signals_block.strip())
    parts.append(f"Document text:\n{sample.document_text}")
    return "\n\n".join(parts)


def _normalise_pages(pages: list[PageText] | None, extracted_text: str) -> list[PageText]:
    if pages:
        out = [
            PageText(p.page_number, (p.text or "").strip())
            for p in pages
            if (p.text or "").strip()
        ]
        if out:
            return out
    cleaned = (extracted_text or "").strip()
    if not cleaned:
        return []
    parts = [part.strip() for part in re.split(r"\n{2,}", cleaned) if part.strip()]
    if len(parts) <= 1:
        return [PageText(1, cleaned)]
    return [PageText(i + 1, part) for i, part in enumerate(parts)]


def _sample_windows(pages: list[PageText], token_budget: int) -> str:
    """Take beginning / early-middle / late-middle / ending windows."""
    budgets = (
        max(1, int(token_budget * 0.30)),
        max(1, int(token_budget * 0.20)),
        max(1, int(token_budget * 0.20)),
        max(1, int(token_budget * 0.30)),
    )
    # Adjust last window so total does not exceed budget after rounding.
    used = sum(budgets[:3])
    budgets = (budgets[0], budgets[1], budgets[2], max(1, token_budget - used))

    joined = "\n\n".join(p.text for p in pages)
    # Character index anchors as fractions of full text.
    anchors = (0.0, 0.33, 0.66, 1.0)
    labels = ("BEGINNING", "EARLY_MIDDLE", "LATE_MIDDLE", "ENDING")
    sections: list[str] = []
    for label, frac, budget in zip(labels, anchors, budgets, strict=True):
        if label == "BEGINNING":
            chunk = _take_tokens_from_start(joined, budget)
        elif label == "ENDING":
            chunk = _take_tokens_from_end(joined, budget)
        else:
            center = int(len(joined) * frac)
            chunk = _take_tokens_around(joined, center, budget)
        if chunk.strip():
            sections.append(f"[{label}]\n{chunk.strip()}")
    return "\n\n".join(sections)


def _take_tokens_from_start(text: str, budget: int) -> str:
    if estimate_tokens(text) <= budget:
        return text
    # Binary-search a prefix by character length.
    lo, hi = 0, len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip()
        if estimate_tokens(candidate) <= budget:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _take_tokens_from_end(text: str, budget: int) -> str:
    if estimate_tokens(text) <= budget:
        return text
    lo, hi = 0, len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[len(text) - mid :].lstrip()
        if estimate_tokens(candidate) <= budget:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _take_tokens_around(text: str, center: int, budget: int) -> str:
    if not text:
        return ""
    if estimate_tokens(text) <= budget:
        return text
    # Expand a character window around center until token budget is hit.
    half = max(64, len(text) // 20)
    lo = max(0, center - half)
    hi = min(len(text), center + half)
    best = text[lo:hi]
    while estimate_tokens(best) < budget and (lo > 0 or hi < len(text)):
        lo = max(0, lo - half)
        hi = min(len(text), hi + half)
        best = text[lo:hi]
        half = max(half, (hi - lo) // 4 or 1)
    # Trim if we overshot.
    if estimate_tokens(best) > budget:
        return _take_tokens_from_start(best, budget)
    return best


def _build_signals(*, filename: str, page_count: int | None, text: str) -> str:
    headings = _extract_headings(text, limit=12)
    dates = _DATE_RE.findall(text)[:8]
    orgs = []
    seen: set[str] = set()
    for match in _ORG_TOKEN_RE.finditer(text):
        token = match.group(0)
        if token in seen or len(token) < 3:
            continue
        seen.add(token)
        orgs.append(token)
        if len(orgs) >= 8:
            break

    lines = ["Detected signals:"]
    lines.append(f"- filename: {filename}")
    if page_count is not None:
        lines.append(f"- page_count: {page_count}")
    if headings:
        lines.append("- headings:")
        lines.extend(f"  - {h}" for h in headings)
    if dates:
        lines.append("- dates: " + ", ".join(dates))
    if orgs:
        lines.append("- organisations_or_codes: " + ", ".join(orgs))
    return "\n".join(lines)


def _extract_headings(text: str, *, limit: int) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 120:
            continue
        if not HEADING_RE.match(stripped):
            continue
        key = stripped.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(stripped)
        if len(found) >= limit:
            break
    return found
