"""Backup bundle manifest (format version 1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

FORMAT_VERSION = 1
BUNDLE_EXTENSION = ".folium"
CHECKSUM_ALGORITHM = "sha256"


@dataclass
class BackupManifest:
    format_version: int
    folium_version: str
    created_at: str
    database_schema_version: str
    backup_type: str
    document_count: int
    original_bytes: int
    checksum_algorithm: str
    verification_state: str
    backup_bytes: int | None = None
    installation_id: str | None = None
    source_hostname: str | None = None
    notes: str | None = None
    derived_data_included: bool = False
    storage_keys: list[str] = field(default_factory=list)
    avatar_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Never include secrets — manifest fields are explicit above.
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupManifest:
        required = {
            "format_version",
            "folium_version",
            "created_at",
            "database_schema_version",
            "backup_type",
            "document_count",
            "original_bytes",
            "checksum_algorithm",
            "verification_state",
        }
        missing = required - set(data)
        if missing:
            raise ValueError(f"Manifest missing fields: {', '.join(sorted(missing))}")
        return cls(
            format_version=int(data["format_version"]),
            folium_version=str(data["folium_version"]),
            created_at=str(data["created_at"]),
            database_schema_version=str(data["database_schema_version"]),
            backup_type=str(data["backup_type"]),
            document_count=int(data["document_count"]),
            original_bytes=int(data["original_bytes"]),
            checksum_algorithm=str(data["checksum_algorithm"]),
            verification_state=str(data["verification_state"]),
            backup_bytes=int(data["backup_bytes"]) if data.get("backup_bytes") is not None else None,
            installation_id=str(data["installation_id"]) if data.get("installation_id") else None,
            source_hostname=str(data["source_hostname"]) if data.get("source_hostname") else None,
            notes=str(data["notes"]) if data.get("notes") else None,
            derived_data_included=bool(data.get("derived_data_included", False)),
            storage_keys=list(data.get("storage_keys") or []),
            avatar_keys=list(data.get("avatar_keys") or []),
        )


def utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

def bundle_filename(record_id: str) -> str:
    return f"folium-{utc_timestamp()}-{record_id}.folium"
