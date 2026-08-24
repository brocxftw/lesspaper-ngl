"""Safe path confinement for the backup repository."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from lesspaper_ngl.core.config import Settings, get_settings
from lesspaper_ngl.core.exceptions import ValidationError

_BUNDLE_NAME_RE = re.compile(r"^folium-[0-9]{8}T[0-9]{6}Z-[0-9a-f-]{36}\.folium$", re.IGNORECASE)
_SAFE_RELATIVE = re.compile(r"^[a-zA-Z0-9._/-]+$")


@dataclass
class RepositoryHealth:
    configured: bool
    exists: bool
    readable: bool
    writable: bool
    path: str
    free_bytes: int | None
    message: str

    @property
    def available(self) -> bool:
        return self.configured and self.exists and self.readable and self.writable


def _confine(root: Path, key: str) -> Path:
    if not key or key.startswith("/") or "\\" in key or ".." in key.split("/"):
        raise ValidationError("Invalid backup path")
    root_resolved = root.resolve()
    candidate = (root / key).resolve()
    if not str(candidate).startswith(str(root_resolved) + os.sep) and candidate != root_resolved:
        raise ValidationError("Path traversal rejected")
    return candidate


def repository_root(settings: Settings | None = None) -> Path:
    return (settings or get_settings()).backups_path


def repository_path(subdir: str = "", settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    root = repository_root(settings)
    subdir = (subdir or "").strip().strip("/")
    if not subdir:
        return root
    if not _SAFE_RELATIVE.match(subdir):
        raise ValidationError("Invalid backup repository subdirectory")
    return _confine(root, subdir)


def bundle_path(filename: str, subdir: str = "", settings: Settings | None = None) -> Path:
    if not _BUNDLE_NAME_RE.match(filename):
        raise ValidationError("Invalid backup filename")
    repo = repository_path(subdir, settings)
    return _confine(repo, filename)


def relative_key(filename: str, subdir: str = "") -> str:
    subdir = (subdir or "").strip().strip("/")
    if subdir:
        return f"{subdir}/{filename}"
    return filename


def check_repository_health(subdir: str = "", settings: Settings | None = None) -> RepositoryHealth:
    settings = settings or get_settings()
    path = repository_path(subdir, settings)
    configured = bool(settings.backups_path)
    exists = path.exists()
    readable = os.access(path, os.R_OK) if exists else False
    writable = False
    free_bytes: int | None = None
    message = "ok"
    if not configured:
        message = "Backup path is not configured"
    elif not exists:
        message = "Backup repository does not exist"
    elif not readable:
        message = "Backup repository is not readable"
    else:
        try:
            probe = path / ".folium_backup_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            writable = True
        except OSError:
            message = "Backup repository is not writable"
        try:
            stat = os.statvfs(path)
            free_bytes = stat.f_bavail * stat.f_frsize
        except OSError:
            free_bytes = None
    return RepositoryHealth(
        configured=configured,
        exists=exists,
        readable=readable,
        writable=writable,
        path=str(path),
        free_bytes=free_bytes,
        message=message,
    )
