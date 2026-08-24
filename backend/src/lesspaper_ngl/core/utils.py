"""Slug helpers and misc utilities."""

from __future__ import annotations

import re
import unicodedata


def slugify(value: str, *, max_length: int = 128) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[-\s]+", "-", value).strip("-")
    return value[:max_length] or "item"
