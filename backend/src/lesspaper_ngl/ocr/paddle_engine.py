"""PaddleOCR PP-OCRv6 engine (CPU) with process-local caching.

PaddlePaddle is not reliable when constructed/run across arbitrary thread-pool
workers (``asyncio.to_thread`` default executor). All engine load + predict
work is pinned to a single dedicated OCR thread.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

# lesspaper-ngl / legacy Tesseract-style codes → PaddleOCR lang.
_LANG_MAP: dict[str, str] = {
    "eng": "en",
    "en": "en",
    "chi_sim": "ch",
    "ch": "ch",
    "chinese_cht": "chinese_cht",
    "chi_tra": "chinese_cht",
    "rus": "ru",
    "ru": "ru",
    "ara": "ar",
    "ar": "ar",
    "fra": "fr",
    "fr": "fr",
    "deu": "german",
    "ger": "german",
    "german": "german",
    "jpn": "japan",
    "japan": "japan",
    "kor": "korean",
    "korean": "korean",
}

_engines: dict[str, Any] = {}
_engines_lock = threading.Lock()
_import_error: str | None = None

# One worker thread: Paddle init + inference must stay on the same thread.
_ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paddle-ocr")
_ocr_thread_ident: int | None = None
_ocr_thread_ident_lock = threading.Lock()

T = TypeVar("T")


def map_ocr_language(language: str | None) -> str:
    """Map lesspaper-ngl OCR_LANGUAGE / document.language codes to Paddle `lang`."""
    raw = (language or "eng").strip().lower().replace("-", "_")
    if not raw:
        return "en"
    if raw in _LANG_MAP:
        return _LANG_MAP[raw]
    # Pass through unknown codes; Paddle may accept them or fail clearly.
    return raw


def paddle_ocr_available() -> bool:
    """True when the paddleocr package is installed.

    Uses ``find_spec`` so the parent worker does not import PaddleOCR (which
    would permanently inflate RSS). Actual import happens only inside the OCR
    subprocess (or when ``OCR_IN_PROCESS`` forces in-process OCR).
    """
    global _import_error
    try:
        import importlib.util

        spec = importlib.util.find_spec("paddleocr")
    except Exception as exc:  # pragma: no cover - env dependent
        _import_error = str(exc)
        return False
    if spec is None:
        _import_error = "paddleocr is not installed"
        return False
    return True


def get_paddle_import_error() -> str | None:
    return _import_error


def get_ocr_executor() -> ThreadPoolExecutor:
    """Dedicated single-thread executor for PaddleOCR work."""
    return _ocr_executor


def run_on_ocr_thread(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run ``fn`` on the dedicated OCR thread (inline if already on it)."""
    global _ocr_thread_ident

    # ThreadPoolExecutor names workers "{prefix}_{n}". Never submit from the
    # OCR thread back into the same max_workers=1 pool (deadlock).
    if threading.current_thread().name.startswith("paddle-ocr"):
        with _ocr_thread_ident_lock:
            _ocr_thread_ident = threading.get_ident()
        return fn(*args, **kwargs)

    if _ocr_thread_ident is not None and threading.get_ident() == _ocr_thread_ident:
        return fn(*args, **kwargs)

    def _call() -> T:
        global _ocr_thread_ident
        with _ocr_thread_ident_lock:
            _ocr_thread_ident = threading.get_ident()
        return fn(*args, **kwargs)

    return _ocr_executor.submit(_call).result()


def get_paddle_ocr(language: str | None = None) -> Any:
    """Return a process-cached PaddleOCR instance for the mapped language.

    Must be called from the dedicated OCR thread (see ``run_on_ocr_thread``).
    """
    lang = map_ocr_language(language)
    with _engines_lock:
        cached = _engines.get(lang)
        if cached is not None:
            return cached

        try:
            from paddleocr import PaddleOCR
        except Exception as exc:
            global _import_error
            _import_error = str(exc)
            raise RuntimeError(
                "PaddleOCR is not installed. Install the lesspaper-ngl OCR extra "
                "(paddlepaddle CPU + paddleocr)."
            ) from exc

        logger.info("Loading PaddleOCR PP-OCRv6 small (lang=%s, device=cpu)", lang)
        engine = PaddleOCR(
            # Small tier: PP-OCRv6 on CPU without medium's RAM spike (OOM-prone on ~8GB hosts).
            text_detection_model_name="PP-OCRv6_small_det",
            text_recognition_model_name="PP-OCRv6_small_rec",
            lang=lang,
            device="cpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # PaddlePaddle 3.3 + oneDNN/PIR crashes on CPU; force plain paddle runner.
            enable_mkldnn=False,
        )
        _engines[lang] = engine
        return engine


def _rec_texts_from_result(result: Any) -> list[str]:
    """Extract recognition strings from a PaddleOCR predict() result."""
    texts: list[str] = []
    if result is None:
        return texts

    items = result if isinstance(result, (list, tuple)) else [result]
    for item in items:
        chunk = _rec_texts_from_item(item)
        texts.extend(chunk)
    return [t.strip() for t in texts if t and str(t).strip()]


def _rec_texts_from_item(item: Any) -> list[str]:
    if item is None:
        return []
    if isinstance(item, dict):
        if "rec_texts" in item:
            return [str(t) for t in (item.get("rec_texts") or [])]
        inner = item.get("res")
        if isinstance(inner, dict) and "rec_texts" in inner:
            return [str(t) for t in (inner.get("rec_texts") or [])]
        return []

    # OCRResult-like objects (PaddleOCR 3.x)
    rec = getattr(item, "rec_texts", None)
    if rec is not None:
        return [str(t) for t in rec]

    as_json = getattr(item, "json", None)
    if callable(as_json):
        try:
            as_json = as_json()
        except Exception:
            as_json = None
    if isinstance(as_json, dict):
        return _rec_texts_from_item(as_json)

    # Some builds expose .get("rec_texts")
    getter = getattr(item, "get", None)
    if callable(getter):
        value = getter("rec_texts")
        if value is not None:
            return [str(t) for t in value]
        nested = getter("res")
        if nested is not None:
            return _rec_texts_from_item(nested)

    return []


def join_rec_texts(result: Any) -> str:
    """Join OCR recognition lines into a single page/document string."""
    return "\n".join(_rec_texts_from_result(result)).strip()


def _ocr_image_on_thread(path: Path | str, *, language: str | None = None) -> str:
    image_path = Path(path)
    if not image_path.is_file():
        logger.warning("OCR image missing: %s", image_path)
        return ""

    try:
        engine = get_paddle_ocr(language)
        result = engine.predict(str(image_path))
        return join_rec_texts(result)
    except Exception:
        logger.exception("PaddleOCR failed for %s", image_path)
        return ""


def ocr_image(path: Path | str, *, language: str | None = None) -> str:
    """Run PP-OCRv6 on an image path and return plain text."""
    return run_on_ocr_thread(_ocr_image_on_thread, path, language=language)


def clear_engine_cache() -> None:
    """Drop cached engines (tests)."""
    with _engines_lock:
        _engines.clear()
