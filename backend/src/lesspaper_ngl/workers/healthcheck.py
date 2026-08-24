"""Synchronous worker liveness check for container healthchecks."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

WORKER_HEARTBEAT_KEY = "worker_heartbeat"
WORKER_HEARTBEAT_STALE_SECONDS = 90


def parse_heartbeat_at(value: Any) -> datetime | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("at")
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def heartbeat_is_fresh(
    last_seen: datetime | None,
    *,
    now: datetime | None = None,
    stale_after_seconds: float = WORKER_HEARTBEAT_STALE_SECONDS,
) -> bool:
    if last_seen is None:
        return False
    current = now or datetime.now(UTC)
    return last_seen >= current - timedelta(seconds=stale_after_seconds)


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def read_heartbeat_value_sync() -> Any:
    url = (os.environ.get("DATABASE_URL_SYNC") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL_SYNC is not set")
    import psycopg

    with psycopg.connect(_psycopg_url(url), connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT value FROM app_settings WHERE key = %s",
            (WORKER_HEARTBEAT_KEY,),
        )
        row = cur.fetchone()
    if not row:
        return None
    value = row[0]
    if isinstance(value, str):
        return json.loads(value)
    return value


def main() -> int:
    try:
        value = read_heartbeat_value_sync()
    except Exception as exc:
        print(f"worker healthcheck failed: {exc}", file=sys.stderr)
        return 1
    last_seen = parse_heartbeat_at(value)
    if heartbeat_is_fresh(last_seen):
        return 0
    print("worker heartbeat missing or stale", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
