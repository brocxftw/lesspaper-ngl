"""Best-effort structured application event persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete

from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.redaction import redact, redact_text
from lesspaper_ngl.db.session import get_session_factory
from lesspaper_ngl.models import ApplicationLog

ALLOWED_CONTEXT_KEYS = {
    "document_id",
    "provider",
    "model",
    "duration_ms",
    "method",
    "path",
    "status_code",
    "job_id",
    "job_type",
}


async def persist_event(
    *,
    level: str,
    service: str,
    module: str,
    message: str,
    request_id: str | None = None,
    context: dict[str, Any] | None = None,
    stack_trace: str | None = None,
) -> None:
    safe_context = {
        key: redact(value) for key, value in (context or {}).items() if key in ALLOWED_CONTEXT_KEYS
    }
    factory = get_session_factory()
    try:
        async with factory() as session:
            cutoff = datetime.now(UTC) - timedelta(
                days=get_settings().application_log_retention_days
            )
            session.add(
                ApplicationLog(
                    level=level[:16],
                    service=service[:32],
                    module=module[:256],
                    message=redact_text(message)[:10000],
                    request_id=request_id[:64] if request_id else None,
                    context=safe_context,
                    stack_trace=redact_text(stack_trace)[:50000] if stack_trace else None,
                )
            )
            await session.execute(delete(ApplicationLog).where(ApplicationLog.timestamp < cutoff))
            await session.commit()
    except Exception:
        # Logging must never make an application request or worker job fail.
        return
