"""Resolve and cache the lesspaper-ngl app version from git history."""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

# Fallback when git metadata is unavailable (e.g. packaged installs).
_FALLBACK = "0.1.0"


def normalize_version(value: str) -> str:
    """Strip whitespace and a leading ``v`` from tagged release strings."""
    text = value.strip()
    if len(text) > 1 and text[0] in {"v", "V"} and text[1].isdigit():
        return text[1:]
    return text


def is_prerelease_version(value: str) -> bool:
    """True when the version has a semver prerelease suffix (``0.1.24-beta.1``)."""
    return "-" in normalize_version(value)


def _repo_root() -> Path | None:
    here = Path(__file__).resolve()
    # backend/src/lesspaper_ngl/core/version.py → repo root is parents[4]
    candidates = [
        here.parents[4] if len(here.parents) > 4 else None,
        here.parents[3] if len(here.parents) > 3 else None,
        Path.cwd(),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        if (candidate / ".git").exists() or (candidate / "backend" / "pyproject.toml").exists():
            return candidate
    return None


def _git_describe(cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty", "--abbrev=7"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """Return the app version, resolved once and kept in process memory."""
    env = normalize_version(
        os.environ.get("LESSPAPER_NGL_VERSION")
        or os.environ.get("FOLIUM_VERSION")
        or ""
    )
    if env:
        return env

    root = _repo_root()
    if root is not None:
        described = _git_describe(root)
        if described:
            return normalize_version(described)

    return _FALLBACK
