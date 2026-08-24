"""Build and read .folium tar bundles."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
from collections.abc import Iterable
from pathlib import Path

from lesspaper_ngl.backup.manifest import BackupManifest

MAX_TAR_MEMBER_BYTES = 10 * 1024 * 1024 * 1024  # 10 GiB per member
MAX_TAR_TOTAL_BYTES = 500 * 1024 * 1024 * 1024  # 500 GiB bundle


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_file(src: Path, dest: Path) -> None:
    """Copy file bytes; preserve metadata when the destination filesystem allows it.

    CIFS/SMB bind mounts often reject ``utime`` (``PermissionError: Operation not
    permitted``), which breaks ``shutil.copy2``. Content is always copied; metadata
    preservation is best-effort.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    try:
        shutil.copystat(src, dest, follow_symlinks=True)
    except OSError:
        pass


def write_checksums(root: Path, members: Iterable[Path]) -> None:
    lines: list[str] = []
    for member in sorted(members, key=lambda p: str(p.relative_to(root))):
        rel = member.relative_to(root).as_posix()
        lines.append(f"{_sha256_file(member)}  {rel}\n")
    (root / "checksums.sha256").write_text("".join(lines), encoding="utf-8")


def verify_checksums(root: Path) -> None:
    checksums_path = root / "checksums.sha256"
    if not checksums_path.exists():
        raise ValueError("checksums.sha256 missing")
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(None, 1)
        rel = rel.strip()
        target = root / rel
        if not target.is_file():
            raise ValueError(f"Checksum target missing: {rel}")
        if _sha256_file(target) != digest:
            raise ValueError(f"Checksum mismatch: {rel}")


def _safe_tar_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    name = tarinfo.name.replace("\\", "/")
    if name.startswith("/") or ".." in name.split("/"):
        return None
    if tarinfo.size > MAX_TAR_MEMBER_BYTES:
        raise ValueError(f"Archive member too large: {name}")
    if tarinfo.issym() or tarinfo.islnk():
        return None
    return tarinfo


def create_bundle_archive(staging_dir: Path, bundle_path: Path) -> int:
    """Write staging_dir contents to bundle_path atomically. Returns size bytes."""
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = bundle_path.with_suffix(bundle_path.suffix + ".part")
    total = 0
    with tarfile.open(tmp, "w") as tar:
        for path in sorted(staging_dir.rglob("*")):
            if path.is_file():
                arcname = path.relative_to(staging_dir).as_posix()
                tar.add(path, arcname=arcname, filter=_safe_tar_filter)
                total += path.stat().st_size
                if total > MAX_TAR_TOTAL_BYTES:
                    raise ValueError("Backup bundle exceeds maximum size")
    os.replace(tmp, bundle_path)
    return bundle_path.stat().st_size


def extract_bundle(bundle_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    total = 0
    with tarfile.open(bundle_path, "r") as tar:
        for member in tar.getmembers():
            name = member.name.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"Unsafe archive path: {name}")
            if member.size > MAX_TAR_MEMBER_BYTES:
                raise ValueError(f"Archive member too large: {name}")
            total += member.size
            if total > MAX_TAR_TOTAL_BYTES:
                raise ValueError("Backup bundle exceeds maximum size")
        tar.extractall(dest, members=tar.getmembers(), filter="data")


def read_manifest_from_staging(staging_dir: Path) -> BackupManifest:
    manifest_path = staging_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("manifest.json missing")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return BackupManifest.from_dict(data)


def write_manifest(staging_dir: Path, manifest: BackupManifest) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def cleanup_staging(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def cleanup_temp_glob(repo: Path, pattern: str = ".folium-backup-*") -> None:
    if not repo.exists():
        return
    for entry in repo.glob(pattern):
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        elif entry.is_file():
            entry.unlink(missing_ok=True)
