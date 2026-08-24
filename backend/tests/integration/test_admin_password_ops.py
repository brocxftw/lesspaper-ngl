"""Admin password ops: resolve admin, set password, consume owner."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from lesspaper_ngl.auth.passwords import verify_password
from lesspaper_ngl.cli import _reset_admin_password
from lesspaper_ngl.db.session import get_session_factory
from lesspaper_ngl.main import app
from lesspaper_ngl.models import User
from lesspaper_ngl.services import users as user_service


@pytest.mark.asyncio
async def test_admin_set_password_for_other_user(auth_client: AsyncClient) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as guest:
        reg = await guest.post(
            "/api/auth/register",
            json={
                "username": "pw_target",
                "password": "password123",
                "display_name": "Target",
            },
        )
        assert reg.status_code == 200, reg.text
        user_id = reg.json()["user"]["id"]

    resp = await auth_client.post(
        f"/api/users/{user_id}/password",
        json={"password": "brandnew99"},
    )
    assert resp.status_code == 200, resp.text

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as guest:
        bad = await guest.post(
            "/api/auth/login",
            json={"username": "pw_target", "password": "password123"},
        )
        assert bad.status_code == 401
        good = await guest.post(
            "/api/auth/login",
            json={"username": "pw_target", "password": "brandnew99"},
        )
        assert good.status_code == 200


@pytest.mark.asyncio
async def test_resolve_admin_and_consume_owner(db_session) -> None:
    admin = await user_service.resolve_admin_user(db_session)
    assert admin.is_admin is True
    assert admin.username == "admin"

    by_name = await user_service.resolve_admin_user(db_session, username="admin")
    assert by_name.id == admin.id

    owner = await user_service.resolve_consume_owner(db_session)
    assert owner.id == admin.id


@pytest.mark.asyncio
async def test_cli_reset_admin_password(db_session) -> None:
    await _reset_admin_password("admin", "cli-reset-password", skip_confirm=True)

    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one()
        assert verify_password(user.password_hash, "cli-reset-password")
        await user_service.admin_set_password(session, user.id, "testpass")
        await session.commit()
