"""Admin-only structured lesspaper-ngl application logs."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from lesspaper_ngl.api.schemas import ApplicationLogListOut, ApplicationLogOut, MessageOut
from lesspaper_ngl.auth.deps import AdminUser, SafeSession
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.redaction import csv_safe, redact, redact_text
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import ApplicationLog

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _start_for(value: str) -> datetime:
    now = datetime.now(UTC)
    return {
        "1h": now - timedelta(hours=1),
        "24h": now - timedelta(days=1),
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
    }[value]


def _filters(
    search: str | None, level: str | None, service: str | None, range: str
) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = [ApplicationLog.timestamp >= _start_for(range)]
    if search:
        pattern = f"%{search[:200]}%"
        clauses.append(
            or_(
                ApplicationLog.message.ilike(pattern),
                ApplicationLog.module.ilike(pattern),
                ApplicationLog.request_id.ilike(pattern),
            )
        )
    if level:
        clauses.append(ApplicationLog.level == level.upper())
    if service:
        clauses.append(ApplicationLog.service == service)
    return clauses


@router.get("", response_model=ApplicationLogListOut)
async def list_logs(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None, max_length=200),
    level: str | None = Query(default=None, pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    service: str | None = Query(default=None, pattern="^(api|worker)$"),
    range: str = Query(default="24h", pattern="^(1h|24h|7d|30d)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ApplicationLogListOut:
    clauses = _filters(search, level, service, range)
    total = int(
        (await db.execute(select(func.count(ApplicationLog.id)).where(*clauses))).scalar_one()
    )
    rows = (
        (
            await db.execute(
                select(ApplicationLog)
                .where(*clauses)
                .order_by(ApplicationLog.timestamp.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return ApplicationLogListOut(
        items=[
            ApplicationLogOut(
                id=row.id,
                timestamp=row.timestamp,
                level=row.level,
                service=row.service,
                module=row.module,
                message=redact_text(row.message),
                request_id=row.request_id,
                context=redact(row.context),
                stack_trace=redact_text(row.stack_trace) if row.stack_trace else None,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        retention_days=get_settings().application_log_retention_days,
    )


@router.get("/export")
async def export_logs(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None, max_length=200),
    level: str | None = Query(default=None, pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    service: str | None = Query(default=None, pattern="^(api|worker)$"),
    range: str = Query(default="24h", pattern="^(1h|24h|7d|30d)$"),
) -> Response:
    rows = (
        (
            await db.execute(
                select(ApplicationLog)
                .where(*_filters(search, level, service, range))
                .order_by(ApplicationLog.timestamp.desc())
                .limit(10_000)
            )
        )
        .scalars()
        .all()
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "level", "service", "module", "message", "request_id"])
    for row in rows:
        writer.writerow(
            [
                csv_safe(row.timestamp.isoformat()),
                csv_safe(row.level),
                csv_safe(row.service),
                csv_safe(row.module),
                csv_safe(row.message),
                csv_safe(row.request_id),
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="folium-application-logs.csv"'},
    )


@router.delete("", response_model=MessageOut)
async def clear_logs(
    _sess: SafeSession,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    count = int((await db.execute(select(func.count(ApplicationLog.id)))).scalar_one())
    await db.execute(delete(ApplicationLog))
    return MessageOut(message=f"Cleared {count} application log events")
