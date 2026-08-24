"""Parent-side OCR subprocess client (streams NDJSON page events)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from lesspaper_ngl.ocr.subprocess_protocol import (
    OcrDoneEvent,
    OcrErrorEvent,
    OcrPageEvent,
    OcrProgressEvent,
    parse_event_line,
)

logger = logging.getLogger(__name__)

OnProgress = Callable[[int, int], None]
OnPage = Callable[[int, str], None]


class OcrSubprocessError(RuntimeError):
    """Raised when the OCR child fails or returns an error event."""


def run_ocr_subprocess(
    *,
    mode: str,
    path: Path,
    language: str,
    dpi: int = 150,
    timeout_seconds: float = 3600.0,
    on_progress: OnProgress | None = None,
    on_page: OnPage | None = None,
) -> OcrDoneEvent:
    """Spawn ``python -m lesspaper_ngl.ocr.subprocess_runner`` and consume NDJSON events.

    Returns the final ``done`` event. Raises ``OcrSubprocessError`` on failure.
    """
    if mode not in {"pdf", "image"}:
        raise ValueError(f"unsupported OCR mode: {mode}")

    cmd = [
        sys.executable,
        "-m",
        "lesspaper_ngl.ocr.subprocess_runner",
        "--mode",
        mode,
        "--path",
        str(path),
        "--language",
        language,
        "--dpi",
        str(dpi),
    ]
    env = os.environ.copy()
    env.pop("OCR_IN_PROCESS", None)

    logger.info("Starting OCR subprocess mode=%s path=%s dpi=%s", mode, path, dpi)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except OSError as exc:
        raise OcrSubprocessError(f"failed to start OCR subprocess: {exc}") from exc

    done: OcrDoneEvent | None = None
    error_message: str | None = None
    stderr = ""
    deadline = time.monotonic() + max(timeout_seconds, 1.0)

    try:
        assert proc.stdout is not None
        while True:
            if time.monotonic() > deadline:
                raise OcrSubprocessError(
                    f"OCR subprocess timed out after {timeout_seconds}s"
                )
            raw_line = proc.stdout.readline()
            if raw_line == "":
                break
            try:
                event = parse_event_line(raw_line)
            except Exception:
                logger.warning("Ignoring malformed OCR event: %r", raw_line[:200])
                continue
            if isinstance(event, OcrProgressEvent):
                if on_progress is not None:
                    on_progress(event.done, event.total)
            elif isinstance(event, OcrPageEvent):
                if on_page is not None:
                    on_page(event.page_number, event.text)
            elif isinstance(event, OcrDoneEvent):
                done = event
            elif isinstance(event, OcrErrorEvent):
                error_message = event.message

        if proc.stderr is not None:
            stderr = proc.stderr.read()
        returncode = proc.wait(timeout=30)
    except OcrSubprocessError:
        _kill(proc)
        raise
    except Exception as exc:
        _kill(proc)
        raise OcrSubprocessError(f"OCR subprocess failed: {exc}") from exc
    finally:
        if proc.poll() is None:
            _kill(proc)

    if error_message:
        raise OcrSubprocessError(error_message)
    if returncode != 0:
        detail = (stderr or "").strip()
        raise OcrSubprocessError(
            f"OCR subprocess exited {returncode}"
            + (f": {detail[:500]}" if detail else "")
        )
    if done is None:
        raise OcrSubprocessError("OCR subprocess ended without a done event")
    return done


def _kill(proc: subprocess.Popen[str]) -> None:
    with_context = proc.poll()
    if with_context is not None:
        return
    try:
        proc.kill()
    except OSError:
        return
    try:
        proc.wait(timeout=30)
    except Exception:
        pass
