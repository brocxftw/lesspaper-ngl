"""MIME validation and filename normalisation."""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.exceptions import ValidationError

# Magic signatures for supported types
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
]

_EXT_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._\- ()\[\]]+")


def detect_mime(data: bytes, filename: str) -> str:
    for sig, mime in _SIGNATURES:
        if data.startswith(sig):
            # Distinguish DOCX from other ZIPs by extension
            if mime.endswith("wordprocessingml.document"):
                ext = Path(filename).suffix.lower()
                if ext != ".docx":
                    continue
            return mime
    # Text heuristics
    ext = Path(filename).suffix.lower()
    if ext in {".txt", ".md", ".markdown"}:
        try:
            data.decode("utf-8")
            return _EXT_MIME.get(ext, "text/plain")
        except UnicodeDecodeError as exc:
            raise ValidationError("Text file is not valid UTF-8") from exc
    guessed, _ = mimetypes.guess_type(filename)
    if guessed and guessed in get_settings().allowed_mimes:
        return guessed
    if ext in _EXT_MIME:
        return _EXT_MIME[ext]
    raise ValidationError(f"Unsupported or unrecognised file type: {filename}")


def assert_allowed_mime(mime: str) -> None:
    if mime not in get_settings().allowed_mimes:
        raise ValidationError(f"Unsupported MIME type: {mime}")


def normalize_filename(filename: str) -> str:
    name = Path(filename).name
    name = name.replace("\x00", "")
    name = _SAFE_FILENAME.sub("_", name).strip(" ._")
    if not name:
        name = "document"
    if len(name) > 200:
        stem = Path(name).stem[:180]
        suffix = Path(name).suffix[:20]
        name = f"{stem}{suffix}"
    return name


_SAFE_FOLDER = re.compile(r'[<>:"|?*\x00-\x1f]')
_MAX_PATH_DEPTH = 32


def sanitize_folder_segment(name: str) -> str:
    """Sanitize a single folder path segment."""
    cleaned = name.replace("\x00", "").replace("/", "_").replace("\\", "_").strip(" .")
    cleaned = _SAFE_FOLDER.sub("_", cleaned)
    if not cleaned or cleaned in {".", ".."}:
        raise ValidationError(f"Invalid folder name: {name!r}")
    if len(cleaned) > 120:
        cleaned = cleaned[:120].rstrip(" .")
    return cleaned


def split_relative_path(relative_path: str) -> tuple[list[str], str]:
    """Split a relative upload path into folder segments and filename.

    Accepts paths like ``MyFolder/sub/doc.pdf`` (POSIX or Windows separators).
    Rejects empty paths and ``..`` traversal.
    """
    raw = relative_path.replace("\\", "/").strip()
    if not raw:
        raise ValidationError("relative_path is required")
    parts = [p for p in raw.split("/") if p and p != "."]
    if not parts:
        raise ValidationError("relative_path is empty")
    if any(p == ".." for p in parts):
        raise ValidationError("Path traversal is not allowed")
    if len(parts) > _MAX_PATH_DEPTH:
        raise ValidationError(f"Path exceeds maximum depth of {_MAX_PATH_DEPTH}")
    filename = normalize_filename(parts[-1])
    segments = [sanitize_folder_segment(p) for p in parts[:-1]]
    return segments, filename


def extension_for_mime(mime: str, filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext:
        return ext
    mapping = {
        "application/pdf": "pdf",
        "image/png": "png",
        "image/jpeg": "jpg",
        "text/plain": "txt",
        "text/markdown": "md",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    }
    return mapping.get(mime, "bin")
