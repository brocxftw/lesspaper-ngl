"""Per-user welcome-tour completion state."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_new_user_requires_onboarding(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/onboarding/status")
    assert response.status_code == 200
    assert response.json()["required"] is True


@pytest.mark.asyncio
async def test_completion_persists_for_the_logged_in_user(auth_client: AsyncClient) -> None:
    response = await auth_client.post("/api/onboarding/complete")
    assert response.status_code == 200
    assert response.json()["required"] is False
    assert (await auth_client.get("/api/onboarding/status")).json()["required"] is False


@pytest.mark.asyncio
async def test_existing_user_marked_complete_is_not_prompted(
    auth_client: AsyncClient,
    db_session,
) -> None:
    from lesspaper_ngl.models import User

    admin = (await db_session.get(User, (await auth_client.get("/api/auth/me")).json()["user"]["id"]))
    assert admin is not None
    admin.onboarding_version = 1
    await db_session.commit()
    assert (await auth_client.get("/api/onboarding/status")).json()["required"] is False
