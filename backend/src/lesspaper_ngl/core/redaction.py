"""Recursive sanitization for logs, diagnostics, and provider errors."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SENSITIVE_KEY = re.compile(
    r"(api[-_]?key|authorization|bearer|cookie|csrf|password|secret|session|token|prompt|document_text)",
    re.I,
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT = re.compile(r"(?i)\b(api[_-]?key|token|password|secret)=([^&\s]+)")
_FILESYSTEM_PATH = re.compile(r"(?<![:\w])/(?:documents|consume|export|tmp|app)(?:/[^\s,;:)]+)*")


def redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
    value = _FILESYSTEM_PATH.sub("[PATH REDACTED]", value)
    try:
        split = urlsplit(value)
        if split.scheme and split.netloc and split.query:
            query = [
                (key, "[REDACTED]" if _SENSITIVE_KEY.search(key) else val)
                for key, val in parse_qsl(split.query, keep_blank_values=True)
            ]
            value = urlunsplit(
                (split.scheme, split.netloc, split.path, urlencode(query), split.fragment)
            )
    except ValueError:
        pass
    return value


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def csv_safe(value: object) -> str:
    text = redact_text("" if value is None else str(value))
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
