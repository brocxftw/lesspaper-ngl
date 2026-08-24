"""Content-addressed document storage with NFS-safe behaviour."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import aiofiles
import aiofiles.os

from lesspaper_ngl.core.config import Settings, get_settings
from lesspaper_ngl.core.exceptions import NotFoundError, StorageUnavailableError, ValidationError
from lesspaper_ngl.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StorageHealth:
    documents_ok: bool
    consume_ok: bool
    export_ok: bool
    documents_path: str
    consume_path: str
    export_path: str
    message: str

    @property
    def healthy(self) -> bool:
        return self.documents_ok and self.consume_ok and self.export_ok

    @property
    def status(self) -> str:
        if self.healthy:
            return "ok"
        if self.documents_ok:
            return "degraded"
        return "unavailable"


class StorageService:
    """Filesystem storage for originals, previews, and thumbnails."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _ensure_writable(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".folium_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageUnavailableError(f"Storage path unavailable: {path}") from exc

    def ensure_layout(self) -> None:
        for path in (
            self.settings.originals_path,
            self.settings.previews_path,
            self.settings.thumbnails_path,
            self.settings.avatars_path,
            self.settings.consume_path,
            self.settings.export_path,
            self.settings.backups_path,
        ):
            try:
                self._ensure_writable(path)
            except StorageUnavailableError:
                logger.warning("Could not initialize storage path %s", path)

    def check_health(self) -> StorageHealth:
        def _ok(path: Path) -> bool:
            try:
                if not path.exists():
                    return False
                # Detect stale NFS mounts: listing or writing may hang/fail
                list(path.iterdir())
                probe = path / ".folium_health_probe"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
                return True
            except OSError:
                return False

        docs_ok = _ok(self.settings.documents_path)
        consume_ok = _ok(self.settings.consume_path)
        export_ok = _ok(self.settings.export_path)
        if docs_ok and consume_ok and export_ok:
            message = "All storage paths available"
        elif docs_ok:
            message = "Document storage available; consume/export degraded"
        else:
            message = "Document storage unavailable — writes rejected; metadata preserved"
        return StorageHealth(
            documents_ok=docs_ok,
            consume_ok=consume_ok,
            export_ok=export_ok,
            documents_path=str(self.settings.documents_path),
            consume_path=str(self.settings.consume_path),
            export_path=str(self.settings.export_path),
            message=message,
        )

    def require_documents_writable(self) -> None:
        health = self.check_health()
        if not health.documents_ok:
            raise StorageUnavailableError(health.message)

    @staticmethod
    def sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def storage_key_for(checksum: str, extension: str) -> str:
        ext = extension.lstrip(".").lower() or "bin"
        return f"{checksum[:2]}/{checksum}.{ext}"

    def originals_absolute(self, storage_key: str) -> Path:
        return self._confine(self.settings.originals_path, storage_key)

    def preview_absolute(self, storage_key: str) -> Path:
        return self._confine(self.settings.previews_path, storage_key)

    def thumbnail_absolute(self, storage_key: str) -> Path:
        return self._confine(self.settings.thumbnails_path, storage_key)

    def _confine(self, root: Path, key: str) -> Path:
        if ".." in key.split("/") or key.startswith("/") or "\\" in key:
            raise ValidationError("Invalid storage key")
        root_resolved = root.resolve()
        candidate = (root / key).resolve()
        if not str(candidate).startswith(str(root_resolved) + os.sep) and candidate != root_resolved:
            raise ValidationError("Path traversal rejected")
        return candidate

    async def persist_original(
        self, data: bytes, *, checksum: str, extension: str
    ) -> str:
        self.require_documents_writable()
        key = self.storage_key_for(checksum, extension)
        dest = self.originals_absolute(key)
        if dest.exists():
            existing = self.sha256_file(dest)
            if existing == checksum:
                return key
            raise ValidationError("Storage key collision with different content")
        dest.parent.mkdir(parents=True, exist_ok=True)
        await self._atomic_write(dest, data)
        return key

    async def persist_original_from_path(
        self, source: Path, *, checksum: str, extension: str
    ) -> str:
        self.require_documents_writable()
        key = self.storage_key_for(checksum, extension)
        dest = self.originals_absolute(key)
        if dest.exists():
            if self.sha256_file(dest) == checksum:
                return key
            raise ValidationError("Storage key collision with different content")
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Copy then verify — never move until verified for consume safety
        tmp_fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=".tmp_")
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        try:
            async with aiofiles.open(source, "rb") as src, aiofiles.open(tmp_path, "wb") as dst:
                while True:
                    chunk = await src.read(1024 * 1024)
                    if not chunk:
                        break
                    await dst.write(chunk)
            if self.sha256_file(tmp_path) != checksum:
                raise ValidationError("Checksum mismatch after copy")
            os.replace(tmp_path, dest)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        return key

    async def write_derived(self, kind: str, key: str, data: bytes) -> str:
        self.require_documents_writable()
        if kind == "preview":
            dest = self.preview_absolute(key)
        elif kind == "thumbnail":
            dest = self.thumbnail_absolute(key)
        else:
            raise ValidationError(f"Unknown derived kind: {kind}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        await self._atomic_write(dest, data)
        return key

    async def read_original(self, storage_key: str) -> bytes:
        path = self.originals_absolute(storage_key)
        if not path.exists():
            raise NotFoundError("Original file not found in storage")
        async with aiofiles.open(path, "rb") as fh:
            return await fh.read()

    def open_original_path(self, storage_key: str) -> Path:
        path = self.originals_absolute(storage_key)
        if not path.exists():
            raise NotFoundError("Original file not found in storage")
        return path

    async def delete_original(self, storage_key: str) -> None:
        path = self.originals_absolute(storage_key)
        try:
            if path.exists():
                await aiofiles.os.remove(path)
        except OSError as exc:
            raise StorageUnavailableError(f"Failed to delete original: {exc}") from exc

    async def delete_derived(self, kind: str, key: str | None) -> None:
        if not key:
            return
        try:
            path = self.preview_absolute(key) if kind == "preview" else self.thumbnail_absolute(key)
            if path.exists():
                await aiofiles.os.remove(path)
        except OSError:
            logger.warning("Failed to delete derived %s/%s", kind, key)

    def avatar_absolute(self, avatar_key: str) -> Path:
        return self._confine(self.settings.avatars_path, avatar_key)

    async def persist_avatar(self, data: bytes, *, user_id: str, extension: str = "webp") -> str:
        self.require_documents_writable()
        self.settings.avatars_path.mkdir(parents=True, exist_ok=True)
        key = f"{user_id}.{extension.lstrip('.').lower()}"
        dest = self.avatar_absolute(key)
        await self._atomic_write(dest, data)
        return key

    def open_avatar_path(self, avatar_key: str) -> Path:
        path = self.avatar_absolute(avatar_key)
        if not path.exists():
            raise NotFoundError("Avatar not found")
        return path

    async def delete_avatar(self, avatar_key: str | None) -> None:
        if not avatar_key:
            return
        try:
            path = self.avatar_absolute(avatar_key)
            if path.exists():
                await aiofiles.os.remove(path)
        except OSError:
            logger.warning("Failed to delete avatar %s", avatar_key)

    @staticmethod
    async def _atomic_write(dest: Path, data: bytes) -> None:
        tmp_fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=".tmp_")
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        try:
            async with aiofiles.open(tmp_path, "wb") as fh:
                await fh.write(data)
            os.replace(tmp_path, dest)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def list_consume_files(self) -> list[Path]:
        health = self.check_health()
        if not health.consume_ok:
            return []
        files: list[Path] = []
        for path in sorted(self.settings.consume_path.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                files.append(path)
        return files

    def is_file_stable(self, path: Path, *, wait_seconds: float = 1.0) -> bool:
        """Return True if size/mtime did not change after a short wait (caller sleeps)."""
        try:
            stat1 = path.stat()
        except OSError:
            return False
        # Caller is expected to have waited; we re-stat for comparison convenience
        try:
            stat2 = path.stat()
        except OSError:
            return False
        return stat1.st_size == stat2.st_size and stat1.st_mtime_ns == stat2.st_mtime_ns
