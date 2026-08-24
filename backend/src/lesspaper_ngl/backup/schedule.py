"""Automatic backup schedule calculation (UTC)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lesspaper_ngl.models import BackupScheduleType, BackupSettings


def _parse_time(text: str) -> tuple[int, int]:
    hour, minute = text.split(":", 1)
    return int(hour), int(minute)


def next_run_after(settings: BackupSettings, after: datetime | None = None) -> datetime:
    after = after or datetime.now(UTC)
    if after.tzinfo is None:
        after = after.replace(tzinfo=UTC)
    hour, minute = _parse_time(settings.backup_time)
    if settings.schedule_type == BackupScheduleType.INTERVAL_HOURS:
        interval = max(1, settings.interval_hours or 24)
        return after + timedelta(hours=interval)
    if settings.schedule_type == BackupScheduleType.WEEKLY:
        weekday = settings.weekday if settings.weekday is not None else 0
        candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = (weekday - candidate.weekday()) % 7
        if days_ahead == 0 and candidate <= after:
            days_ahead = 7
        return candidate + timedelta(days=days_ahead)
    # daily
    candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate
