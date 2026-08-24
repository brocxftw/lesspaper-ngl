"""Worker liveness heartbeat helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lesspaper_ngl.workers.healthcheck import heartbeat_is_fresh, parse_heartbeat_at


def test_parse_heartbeat_at_accepts_iso() -> None:
    seen = parse_heartbeat_at({"at": "2026-08-16T12:00:00+00:00", "worker_id": "w1"})
    assert seen is not None
    assert seen.year == 2026


def test_parse_heartbeat_at_rejects_junk() -> None:
    assert parse_heartbeat_at(None) is None
    assert parse_heartbeat_at({"at": "not-a-date"}) is None


def test_heartbeat_is_fresh_within_threshold() -> None:
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    last = now - timedelta(seconds=30)
    assert heartbeat_is_fresh(last, now=now, stale_after_seconds=90) is True
    assert heartbeat_is_fresh(last, now=now, stale_after_seconds=10) is False
    assert heartbeat_is_fresh(None, now=now) is False
