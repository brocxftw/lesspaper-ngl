"""Backup bundle verification and compatibility checks."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from lesspaper_ngl import __version__
from lesspaper_ngl.backup.bundle import extract_bundle, read_manifest_from_staging, verify_checksums
from lesspaper_ngl.backup.dump import validate_dump_readable
from lesspaper_ngl.backup.manifest import FORMAT_VERSION, BackupManifest
from lesspaper_ngl.models import BackupVerificationStatus


@dataclass
class InspectResult:
    manifest: BackupManifest
    verification_status: BackupVerificationStatus
    compatible: bool
    messages: list[str]


def _alembic_script() -> ScriptDirectory | None:
    from pathlib import Path

    for candidate in (Path("alembic.ini"), Path("/app/alembic.ini")):
        if candidate.exists():
            return ScriptDirectory.from_config(Config(str(candidate)))
    return None


def _current_schema_head() -> str:
    script = _alembic_script()
    if script is None:
        return "unknown"
    return script.get_current_head() or "unknown"


def _known_revisions() -> set[str]:
    script = _alembic_script()
    if script is None:
        return set()
    return {rev.revision for rev in script.walk_revisions()}


def check_version_compatibility(manifest: BackupManifest) -> tuple[bool, list[str]]:
    messages: list[str] = []
    if manifest.format_version != FORMAT_VERSION:
        return False, [f"Unsupported backup format version {manifest.format_version}"]
    app_version = __version__
    backup_ver = _parse_version(manifest.folium_version)
    current_ver = _parse_version(app_version)
    # Skip semver gate when either side is non-semver (e.g. git SHA from describe --always).
    if backup_ver is not None and current_ver is not None and backup_ver > current_ver:
        return False, [
            f"Backup lesspaper-ngl version {manifest.folium_version} is newer than this installation ({app_version})"
        ]
    head = _current_schema_head()
    known = _known_revisions()
    backup_schema = manifest.database_schema_version
    if backup_schema and known and backup_schema not in known:
        return False, [f"Backup schema {backup_schema} is not supported by this installation"]
    if backup_schema and backup_schema != head:
        messages.append(f"Backup schema {backup_schema} will be migrated to {head}")
    messages.append("Backup is compatible with this installation")
    return True, messages


def _parse_version(version: str) -> tuple[int, ...] | None:
    parts: list[int] = []
    normalized = version.strip().lstrip("vV").split("-")[0].split("+")[0]
    # Reject bare non-dotted tokens (git SHAs) — they must not collapse to a fake (0,) semver.
    if "." not in normalized and not normalized.isdigit():
        return None
    for piece in normalized.split("."):
        if piece.isdigit():
            parts.append(int(piece))
        else:
            break
    return tuple(parts) if parts else None


def inspect_bundle_file(bundle_path: Path, *, verify_checksums_flag: bool = True) -> InspectResult:
    messages: list[str] = []
    status = BackupVerificationStatus.UNVERIFIED
    compatible = False
    manifest: BackupManifest | None = None
    with tempfile.TemporaryDirectory(prefix="folium-inspect-") as tmp:
        staging = Path(tmp)
        try:
            extract_bundle(bundle_path, staging)
            manifest = read_manifest_from_staging(staging)
            dump_path = staging / "database" / "lesspaper_ngl.dump"
            if not dump_path.is_file():
                raise ValueError("Database dump missing")
            validate_dump_readable(dump_path)
            if verify_checksums_flag:
                verify_checksums(staging)
            for key in manifest.storage_keys:
                if not (staging / "documents" / "originals" / key).is_file():
                    raise ValueError(f"Missing original in bundle: {key}")
            for key in manifest.avatar_keys:
                if not (staging / "documents" / "avatars" / key).is_file():
                    raise ValueError(f"Missing avatar in bundle: {key}")
            status = BackupVerificationStatus.HEALTHY
        except ValueError as exc:
            messages.append(str(exc))
            status = BackupVerificationStatus.CORRUPTED
        except Exception as exc:  # noqa: BLE001 — operator-facing classification
            messages.append(str(exc))
            status = BackupVerificationStatus.FAILED
    if manifest is None:
        return InspectResult(
            manifest=BackupManifest(
                format_version=0,
                folium_version="unknown",
                created_at="",
                database_schema_version="",
                backup_type="full",
                document_count=0,
                original_bytes=0,
                checksum_algorithm="sha256",
                verification_state=status.value,
            ),
            verification_status=status,
            compatible=False,
            messages=messages or ["Backup bundle could not be read"],
        )
    compatible, compat_msgs = check_version_compatibility(manifest)
    messages.extend(compat_msgs)
    if not compatible:
        status = BackupVerificationStatus.INCOMPATIBLE
    return InspectResult(
        manifest=manifest,
        verification_status=status,
        compatible=compatible,
        messages=messages,
    )


def read_manifest_from_bundle(bundle_path: Path) -> BackupManifest:
    import tarfile

    with tarfile.open(bundle_path, "r") as tar:
        try:
            member = tar.getmember("manifest.json")
        except KeyError as exc:
            raise ValueError("manifest.json missing") from exc
        extracted = tar.extractfile(member)
        if extracted is None:
            raise ValueError("manifest.json unreadable")
        data = json.loads(extracted.read().decode("utf-8"))
    return BackupManifest.from_dict(data)
