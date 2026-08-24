"""Unit tests for OCR-before-AI preflight gating."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lesspaper_ngl.ocr.extractor import ExtractedPage, pages_need_ocr
from lesspaper_ngl.workers.processor import (
    _has_usable_extracted_text,
    _pdf_needs_ocr_before_ai,
)


def _doc(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "extracted_text": "",
        "mime_type": "application/pdf",
        "ocr_completed": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.parametrize(
    ("text", "usable"),
    [
        ("", False),
        ("short", False),
        ("x" * 19, False),
        ("x" * 20, True),
        ("Enough extracted text for filing", True),
    ],
)
def test_has_usable_extracted_text(text: str, usable: bool) -> None:
    assert _has_usable_extracted_text(_doc(extracted_text=text)) is usable


def test_pages_need_ocr_when_empty() -> None:
    assert pages_need_ocr([]) is True
    assert pages_need_ocr([ExtractedPage(1, "")]) is True


def test_pages_need_ocr_when_thin() -> None:
    assert pages_need_ocr([ExtractedPage(1, "x" * 10)]) is True


def test_pages_skip_ocr_when_dense_native_text() -> None:
    assert pages_need_ocr([ExtractedPage(1, "x" * 40)]) is False


def test_pdf_needs_ocr_when_text_thin_and_ocr_not_done() -> None:
    doc = _doc(extracted_text="", ocr_completed=False, mime_type="application/pdf")
    assert _pdf_needs_ocr_before_ai(doc, ocr_enabled=True) is True


def test_pdf_needs_ocr_when_avg_page_text_is_thin() -> None:
    # Usable for the AI min-length check, but still too thin per-page → OCR.
    doc = _doc(extracted_text="x" * 25, ocr_completed=False, mime_type="application/pdf")
    assert _has_usable_extracted_text(doc) is True
    assert _pdf_needs_ocr_before_ai(doc, ocr_enabled=True) is True


def test_pdf_skips_ocr_when_native_text_is_usable() -> None:
    doc = _doc(
        extracted_text="Native PDF text with enough characters here for filing.",
        ocr_completed=False,
        mime_type="application/pdf",
    )
    assert _pdf_needs_ocr_before_ai(doc, ocr_enabled=True) is False


def test_pdf_skips_ocr_when_already_completed() -> None:
    doc = _doc(extracted_text="", ocr_completed=True, mime_type="application/pdf")
    assert _pdf_needs_ocr_before_ai(doc, ocr_enabled=True) is False


def test_non_pdf_never_needs_dedicated_ocr_gate() -> None:
    doc = _doc(extracted_text="", ocr_completed=False, mime_type="image/png")
    assert _pdf_needs_ocr_before_ai(doc, ocr_enabled=True) is False


def test_ocr_disabled_skips_gate() -> None:
    doc = _doc(extracted_text="", ocr_completed=False, mime_type="application/pdf")
    assert _pdf_needs_ocr_before_ai(doc, ocr_enabled=False) is False
