"""Persist AI usage metrics."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import AIUsage


async def record_usage(
    session: AsyncSession,
    *,
    provider: str,
    model: str,
    operation: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    reported_cost: float | None = None,
    estimated_cost: float | None = None,
    cost_currency: str | None = None,
    cost_source: str | None = None,
    duration_ms: int | None = None,
    status: str = "completed",
    is_local: bool = False,
    document_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AIUsage:
    """Record a single AI operation in the usage ledger."""
    row = AIUsage(
        user_id=user_id,
        provider=provider,
        model=model,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reported_cost=reported_cost,
        estimated_cost=estimated_cost,
        cost_currency=cost_currency,
        cost_source=cost_source,
        duration_ms=duration_ms,
        status=status,
        is_local=is_local,
        document_id=document_id,
    )
    session.add(row)
    await session.flush()
    return row
