"""AI usage endpoint aggregation and provider-cost coverage."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.usage import record_usage


@pytest.mark.asyncio
async def test_usage_returns_chart_points_and_openrouter_cost(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await record_usage(
        db_session,
        provider="OpenRouter",
        model="openai/gpt-4o-mini",
        operation="qa",
        input_tokens=120,
        output_tokens=30,
        reported_cost=0.00042,
        cost_currency="USD",
        cost_source="provider",
        duration_ms=250,
    )
    await record_usage(
        db_session,
        provider="OpenRouter",
        model="openai/gpt-4o-mini",
        operation="metadata_suggestion",
        input_tokens=80,
        output_tokens=20,
        duration_ms=150,
    )
    await db_session.commit()

    response = await auth_client.get("/api/ai/usage", params={"range": "today"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["totals"] == {
        "requests": 2,
        "input_tokens": 200,
        "output_tokens": 50,
        "duration_ms": 400,
        "estimated_cost": pytest.approx(0.00042),
        "cost_currency": "USD",
        "cost_coverage": "partial",
    }
    assert payload["time_series"]
    assert payload["time_series"][-1]["requests"] == 2
    assert {item["key"] for item in payload["by_workload"]} == {"chat", "indexing"}
