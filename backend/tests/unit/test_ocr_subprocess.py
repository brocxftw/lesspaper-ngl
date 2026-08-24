"""Tests for OCR subprocess NDJSON protocol and client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lesspaper_ngl.ocr.subprocess_client import OcrSubprocessError, run_ocr_subprocess
from lesspaper_ngl.ocr.subprocess_protocol import (
    OcrDoneEvent,
    OcrErrorEvent,
    OcrPageEvent,
    OcrProgressEvent,
    parse_event_line,
)


def test_parse_progress_page_done() -> None:
    assert parse_event_line('{"type":"progress","done":1,"total":3}') == OcrProgressEvent(
        1, 3
    )
    assert parse_event_line(
        '{"type":"page","page_number":2,"text":"hello"}'
    ) == OcrPageEvent(2, "hello")
    assert parse_event_line(
        '{"type":"done","method":"pymupdf+paddleocr","page_count":2,"language":"eng"}'
    ) == OcrDoneEvent("pymupdf+paddleocr", 2, "eng")


def test_parse_error_event() -> None:
    assert parse_event_line('{"type":"error","message":"boom"}') == OcrErrorEvent("boom")


def test_parse_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="unknown OCR event"):
        parse_event_line('{"type":"nope"}')


def test_run_ocr_subprocess_streams_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class _LineStdout:
        def __init__(self, lines: list[str]):
            self._lines = list(lines)
            self._i = 0

        def readline(self) -> str:
            if self._i >= len(self._lines):
                return ""
            line = self._lines[self._i]
            self._i += 1
            return line

    class _FakeProc:
        def __init__(self, *args, **kwargs):
            events = [
                {"type": "progress", "done": 0, "total": 2},
                {"type": "page", "page_number": 1, "text": "one"},
                {"type": "progress", "done": 1, "total": 2},
                {"type": "page", "page_number": 2, "text": "two"},
                {"type": "progress", "done": 2, "total": 2},
                {
                    "type": "done",
                    "method": "pymupdf+paddleocr",
                    "page_count": 2,
                    "language": "eng",
                },
            ]
            self.stdout = _LineStdout([json.dumps(e) + "\n" for e in events])
            self.stderr = _Empty()
            self._code = 0

        def poll(self):
            return self._code

        def wait(self, timeout=None):
            return self._code

        def kill(self):
            self._code = -9

    class _Empty:
        def read(self):
            return ""

    monkeypatch.setattr("lesspaper_ngl.ocr.subprocess_client.subprocess.Popen", _FakeProc)

    progress: list[tuple[int, int]] = []
    pages: list[tuple[int, str]] = []
    done = run_ocr_subprocess(
        mode="pdf",
        path=pdf,
        language="eng",
        dpi=150,
        on_progress=lambda d, t: progress.append((d, t)),
        on_page=lambda n, t: pages.append((n, t)),
    )
    assert done.page_count == 2
    assert done.method == "pymupdf+paddleocr"
    assert pages == [(1, "one"), (2, "two")]
    assert progress[0] == (0, 2)
    assert progress[-1] == (2, 2)


def test_run_ocr_subprocess_raises_on_error_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "x.png"
    image.write_bytes(b"x")

    class _LineStdout:
        def __init__(self, lines: list[str]):
            self._lines = list(lines)
            self._i = 0

        def readline(self) -> str:
            if self._i >= len(self._lines):
                return ""
            line = self._lines[self._i]
            self._i += 1
            return line

    class _FakeProc:
        def __init__(self, *args, **kwargs):
            self.stdout = _LineStdout(
                [json.dumps({"type": "error", "message": "paddle failed"}) + "\n"]
            )
            self.stderr = type("S", (), {"read": lambda self: ""})()
            self._code = 1

        def poll(self):
            return self._code

        def wait(self, timeout=None):
            return self._code

        def kill(self):
            pass

    monkeypatch.setattr("lesspaper_ngl.ocr.subprocess_client.subprocess.Popen", _FakeProc)

    with pytest.raises(OcrSubprocessError, match="paddle failed"):
        run_ocr_subprocess(mode="image", path=image, language="eng")
