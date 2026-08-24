"""Per-user storage and AI request quota enforcement."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.core.exceptions import NotFoundError, ValidationError
from lesspaper_ngl.models import AIUsage, Document, User


async def storage_usage_bytes(session: AsyncSession, owner_id: uuid.UUID) -> int:
    usage = await session.scalar(
        select(func.coalesce(func.sum(Document.file_size), 0)).where(Document.owner_id == owner_id)
    )
    return int(usage or 0)


async def assert_storage_quota(
    session: AsyncSession,
    owner_id: uuid.UUID,
    additional_bytes: int,
) -> None:
    user = await session.get(User, owner_id)
    if user is None:
        raise NotFoundError("User not found")
    if additional_bytes < 0:
        raise ValidationError("Additional storage bytes cannot be negative")
    if user.storage_quota_bytes is None:
        return
    usage = await storage_usage_bytes(session, owner_id)
    if usage + additional_bytes > user.storage_quota_bytes:
        raise ValidationError("Storage quota exceeded")


async def ai_requests_this_month(session: AsyncSession, user_id: uuid.UUID) -> int:
    now = datetime.now(UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    count = await session.scalar(
        select(func.count())
        .select_from(AIUsage)
        .where(
            AIUsage.user_id == user_id,
            AIUsage.created_at >= month_start,
        )
    )
    return int(count or 0)


async def assert_ai_quota(session: AsyncSession, user_id: uuid.UUID) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    if user.ai_monthly_request_quota is None:
        return
    usage = await ai_requests_this_month(session, user_id)
    if usage >= user.ai_monthly_request_quota:
        raise ValidationError("Monthly AI request quota exceeded")
