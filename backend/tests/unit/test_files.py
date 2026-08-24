"""File utility unit tests."""

from __future__ import annotations

import pytest

from lesspaper_ngl.core.exceptions import ValidationError
from lesspaper_ngl.core.files import detect_mime, normalize_filename
from lesspaper_ngl.storage.service import StorageService


def test_detect_mime_pdf() -> None:
    data = b"%PDF-1.4 test"
    assert detect_mime(data, "doc.pdf") == "application/pdf"


def test_detect_mime_plain_text() -> None:
    data = b"LPPSA refinance RM 420000"
    assert detect_mime(data, "notes.txt") == "text/plain"


def test_normalize_filename_strips_path_and_unsafe_chars() -> None:
    assert normalize_filename("../../etc/passwd") == "passwd"
    assert normalize_filename("  report (final).pdf  ") == "report (final).pdf"
    assert normalize_filename("") == "document"


def test_split_relative_path() -> None:
    import pytest

    from lesspaper_ngl.core.exceptions import ValidationError
    from lesspaper_ngl.core.files import split_relative_path

    segs, name = split_relative_path("Finance/2024/invoice.pdf")
    assert segs == ["Finance", "2024"]
    assert name == "invoice.pdf"

    segs, name = split_relative_path("only.txt")
    assert segs == []
    assert name == "only.txt"

    with pytest.raises(ValidationError):
        split_relative_path("../etc/passwd")

    with pytest.raises(ValidationError):
        split_relative_path("a/../../b.pdf")


def test_storage_key_traversal_rejected() -> None:
    storage = StorageService()
    with pytest.raises(ValidationError):
        storage.originals_absolute("../../../etc/passwd")
    with pytest.raises(ValidationError):
        storage.originals_absolute("/absolute/path.txt")
