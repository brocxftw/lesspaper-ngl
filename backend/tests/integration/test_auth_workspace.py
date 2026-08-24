"""Password reset, avatar, and admin self-protection."""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from PIL import Image


def _png_bytes(size: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color=(40, 120, 80)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_admin_cannot_change_own_quotas(auth_client: AsyncClient) -> None:
    me = await auth_client.get("/api/auth/me")
    assert me.status_code == 200
    admin_id = me.json()["user"]["id"]

    resp = await auth_client.patch(
        f"/api/users/{admin_id}",
        json={"storage_quota_bytes": 1024 * 1024 * 100},
    )
    assert resp.status_code == 422
    assert "quota" in resp.json()["message"].lower()

    resp = await auth_client.patch(
        f"/api/users/{admin_id}",
        json={"clear_ai_quota": True},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_cannot_delete_self(auth_client: AsyncClient) -> None:
    me = await auth_client.get("/api/auth/me")
    admin_id = me.json()["user"]["id"]
    resp = await auth_client.delete(f"/api/users/{admin_id}")
    assert resp.status_code == 422
    assert "yourself" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_password_reset_flow(auth_client: AsyncClient) -> None:
    from httpx import ASGITransport

    from lesspaper_ngl.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as guest:
        reg = await guest.post(
            "/api/auth/register",
            json={
                "username": "reset_user",
                "password": "password123",
                "display_name": "Reset User",
            },
        )
        assert reg.status_code == 200, reg.text

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as guest:
        forgot = await guest.post(
            "/api/auth/forgot-password",
            json={"username": "reset_user"},
        )
        assert forgot.status_code == 200
        assert "admin" in forgot.json()["message"].lower()

        forgot_unknown = await guest.post(
            "/api/auth/forgot-password",
            json={"username": "nobody_here"},
        )
        assert forgot_unknown.status_code == 200
        assert forgot_unknown.json()["message"] == forgot.json()["message"]

    pending = await auth_client.get("/api/users/password-resets")
    assert pending.status_code == 200, pending.text
    assert len(pending.json()) >= 1
    req = next(r for r in pending.json() if r["username"] == "reset_user")

    approved = await auth_client.post(f"/api/users/password-resets/{req['id']}/approve")
    assert approved.status_code == 200, approved.text
    token = approved.json()["reset_url_token"]
    assert token

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as guest:
        valid = await guest.get(
            "/api/auth/reset-password/validate",
            params={"token": token},
        )
        assert valid.status_code == 200
        assert valid.json()["valid"] is True
        assert valid.json()["username"] == "reset_user"

        reset = await guest.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "newpassword99"},
        )
        assert reset.status_code == 200, reset.text

        reuse = await guest.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "anotherpass99"},
        )
        assert reuse.status_code == 422

        login = await guest.post(
            "/api/auth/login",
            json={"username": "reset_user", "password": "newpassword99"},
        )
        assert login.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_reject(auth_client: AsyncClient) -> None:
    from httpx import ASGITransport

    from lesspaper_ngl.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as guest:
        reg = await guest.post(
            "/api/auth/register",
            json={
                "username": "reject_user",
                "password": "password123",
                "display_name": "Reject",
            },
        )
        assert reg.status_code == 200

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as guest:
        await guest.post("/api/auth/forgot-password", json={"username": "reject_user"})

    pending = await auth_client.get("/api/users/password-resets")
    assert pending.status_code == 200, pending.text
    req = next(r for r in pending.json() if r["username"] == "reject_user")
    rejected = await auth_client.post(f"/api/users/password-resets/{req['id']}/reject")
    assert rejected.status_code == 200

    pending2 = await auth_client.get("/api/users/password-resets")
    assert all(r["username"] != "reject_user" for r in pending2.json())


@pytest.mark.asyncio
async def test_avatar_upload_and_remove(auth_client: AsyncClient) -> None:
    me = await auth_client.get("/api/auth/me")
    assert me.json()["user"].get("has_avatar") is False

    upload = await auth_client.post(
        "/api/auth/me/avatar",
        files={"file": ("avatar.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["has_avatar"] is True

    get_av = await auth_client.get("/api/auth/me/avatar")
    assert get_av.status_code == 200
    assert get_av.headers["content-type"].startswith("image/")

    remove = await auth_client.delete("/api/auth/me/avatar")
    assert remove.status_code == 200
    assert remove.json()["has_avatar"] is False

    missing = await auth_client.get("/api/auth/me/avatar")
    assert missing.status_code == 404
