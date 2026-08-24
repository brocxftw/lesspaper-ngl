"""Short-lived OCR child process: load Paddle, emit NDJSON page events, exit.

Run as::

    python -m lesspaper_ngl.ocr.subprocess_runner --mode pdf --path /docs/... --language eng --dpi 150

The parent worker stays lean; when this process exits the kernel reclaims model RAM.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import pymupdf

from lesspaper_ngl.ocr.paddle_engine import ocr_image
from lesspaper_ngl.ocr.subprocess_protocol import encode_event


def _emit(payload: dict) -> None:
    sys.stdout.write(encode_event(payload) + "\n")
    sys.stdout.flush()


def _run_pdf(*, path: Path, language: str, dpi: int) -> None:
    with pymupdf.open(path) as doc:
        total = doc.page_count
        _emit({"type": "progress", "done": 0, "total": total})
        for index in range(total):
            page = doc.load_page(index)
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                pix.save(str(tmp_path))
                del pix
                text = ocr_image(tmp_path, language=language)
            finally:
                tmp_path.unlink(missing_ok=True)
            _emit({"type": "page", "page_number": index + 1, "text": text})
            _emit({"type": "progress", "done": index + 1, "total": total})
        _emit(
            {
                "type": "done",
                "method": "pymupdf+paddleocr",
                "page_count": total,
                "language": language,
            }
        )


def _run_image(*, path: Path, language: str) -> None:
    _emit({"type": "progress", "done": 0, "total": 1})
    text = ocr_image(path, language=language)
    _emit({"type": "page", "page_number": 1, "text": text})
    _emit({"type": "progress", "done": 1, "total": 1})
    _emit(
        {
            "type": "done",
            "method": "paddleocr",
            "page_count": 1,
            "language": language,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lesspaper_ngl.ocr.subprocess_runner")
    parser.add_argument("--mode", choices=("pdf", "image"), required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--language", default="eng")
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args(argv)

    path = args.path
    if not path.is_file():
        _emit({"type": "error", "message": f"File not found: {path}"})
        return 1

    try:
        if args.mode == "pdf":
            _run_pdf(path=path, language=args.language, dpi=max(72, args.dpi))
        else:
            _run_image(path=path, language=args.language)
    except Exception as exc:
        _emit({"type": "error", "message": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
