"""Resolve role-based AI models with one-release legacy compatibility."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.bootstrap import ensure_ai_settings
from lesspaper_ngl.models import (
    AIModelAssignment,
    AIProvider,
    AIWorkloadRole,
)


@dataclass(slots=True)
class ResolvedAssignment:
    role: AIWorkloadRole
    provider: AIProvider | None
    model: str | None
    assignment: AIModelAssignment | None
    legacy_fallback: bool = False


async def ensure_assignments(session: AsyncSession) -> list[AIModelAssignment]:
    settings = await ensure_ai_settings(session)
    existing = {
        row.role: row for row in (await session.execute(select(AIModelAssignment))).scalars()
    }
    legacy: dict[AIWorkloadRole, tuple[object | None, str]] = {
        AIWorkloadRole.INDEXING: (settings.chat_provider_id, "chat_model"),
        AIWorkloadRole.CHAT: (settings.chat_provider_id, "chat_model"),
        AIWorkloadRole.EMBEDDING: (settings.embedding_provider_id, "embedding_model"),
        AIWorkloadRole.VISION: (settings.vision_provider_id, "vision_model"),
    }
    for role, (provider_id, model_field) in legacy.items():
        if role in existing:
            continue
        provider = await session.get(AIProvider, provider_id) if provider_id else None
        row = AIModelAssignment(
            role=role,
            provider_id=provider.id if provider else None,
            model=getattr(provider, model_field, None) if provider else None,
        )
        session.add(row)
        existing[role] = row
    await session.flush()
    return [existing[role] for role in AIWorkloadRole]


async def resolve_assignment(session: AsyncSession, role: AIWorkloadRole) -> ResolvedAssignment:
    row = (
        await session.execute(select(AIModelAssignment).where(AIModelAssignment.role == role))
    ).scalar_one_or_none()
    if row is None:
        rows = await ensure_assignments(session)
        row = next(item for item in rows if item.role == role)
    provider = await session.get(AIProvider, row.provider_id) if row.provider_id else None
    return ResolvedAssignment(role, provider, row.model, row)
