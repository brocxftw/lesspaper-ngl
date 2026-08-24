"""Unit tests for PaddleOCR engine helpers (mocked — no models required)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lesspaper_ngl.ocr import paddle_engine
from lesspaper_ngl.ocr.paddle_engine import (
    clear_engine_cache,
    join_rec_texts,
    map_ocr_language,
    ocr_image,
)


@pytest.fixture(autouse=True)
def _reset_engine_cache() -> None:
    clear_engine_cache()
    yield
    clear_engine_cache()


@pytest.mark.parametrize(
    ("raw", "mapped"),
    [
        ("eng", "en"),
        ("en", "en"),
        ("chi_sim", "ch"),
        ("chi_tra", "chinese_cht"),
        ("rus", "ru"),
        ("ara", "ar"),
        (None, "en"),
        ("", "en"),
        ("FRA", "fr"),
    ],
)
def test_map_ocr_language(raw: str | None, mapped: str) -> None:
    assert map_ocr_language(raw) == mapped


def test_join_rec_texts_from_dict_list() -> None:
    result = [{"rec_texts": ["Hello", "world"]}, {"rec_texts": ["again"]}]
    assert join_rec_texts(result) == "Hello\nworld\nagain"


def test_join_rec_texts_from_nested_res() -> None:
    result = [{"res": {"rec_texts": ["Nested"]}}]
    assert join_rec_texts(result) == "Nested"


def test_join_rec_texts_from_objects() -> None:
    result = [SimpleNamespace(rec_texts=["A", "B"])]
    assert join_rec_texts(result) == "A\nB"


def test_ocr_image_uses_cached_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    calls: list[str] = []

    class _FakeEngine:
        def predict(self, path: str):
            calls.append(path)
            return [{"rec_texts": ["Invoice 42"]}]

    monkeypatch.setattr(paddle_engine, "get_paddle_ocr", lambda language=None: _FakeEngine())
    assert ocr_image(image, language="eng") == "Invoice 42"
    assert calls == [str(image)]


def test_ocr_image_missing_file_returns_empty(tmp_path: Path) -> None:
    assert ocr_image(tmp_path / "missing.png") == ""
