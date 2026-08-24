"""Backup retention policy."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.backup.paths import bundle_path
from lesspaper_ngl.core.logging import get_logger
from lesspaper_ngl.models import (
    BackupRecord,
    BackupRecordStatus,
    BackupSettings,
    BackupVerificationStatus,
)

logger = get_logger(__name__)


async def apply_retention(session: AsyncSession, settings: BackupSettings) -> list[str]:
    """Delete oldest completed backups beyond retention_count. Returns deleted filenames."""
    if settings.retention_count < 1:
        return []
    stmt = (
        select(BackupRecord)
        .where(
            BackupRecord.status == BackupRecordStatus.COMPLETED,
            BackupRecord.verification_status.in_(
                [
                    BackupVerificationStatus.HEALTHY,
                    BackupVerificationStatus.UNVERIFIED,
                ]
            ),
        )
        .order_by(BackupRecord.created_at.asc())
    )
    records = list((await session.execute(stmt)).scalars().all())
    excess = len(records) - settings.retention_count
    if excess <= 0:
        return []
    to_delete = records[:excess]
    deleted: list[str] = []
    for record in to_delete:
        # Do not auto-delete corrupted backups if they are the only copy.
        if record.verification_status == BackupVerificationStatus.CORRUPTED:
            corrupted_only = all(
                r.verification_status == BackupVerificationStatus.CORRUPTED for r in records
            )
            if corrupted_only:
                continue
        try:
            path = bundle_path(record.filename, settings.repository_subdir)
            if path.is_file():
                path.unlink()
        except Exception:  # noqa: BLE001
            logger.warning("Could not delete backup file %s", record.filename, exc_info=True)
        await session.delete(record)
        deleted.append(record.filename)
        logger.info(
            "Retention deleted backup %s at %s",
            record.filename,
            datetime.now(UTC).isoformat(),
        )
    return deleted
