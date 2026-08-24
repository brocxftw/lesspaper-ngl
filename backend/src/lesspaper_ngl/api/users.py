"""Admin user management and invites."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.auth import user_out
from lesspaper_ngl.api.schemas import (
    AdminSetPasswordRequest,
    InviteCreateRequest,
    InviteOut,
    MessageOut,
    PasswordResetRequestOut,
    UserAdminOut,
    UserAdminUpdate,
)
from lesspaper_ngl.auth.deps import AdminUser, SafeSession
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import PasswordResetStatus
from lesspaper_ngl.services import users as user_service
from lesspaper_ngl.storage.service import StorageService

router = APIRouter(prefix="/api/users", tags=["users"])


def _admin_out(user, usage: dict) -> UserAdminOut:
    base = user_out(user)
    return UserAdminOut(
        **base.model_dump(),
        created_at=user.created_at,
        storage_used_bytes=usage["storage_used_bytes"],
        ai_requests_this_month=usage["ai_requests_this_month"],
    )


def _reset_out(req, *, reset_token: str | None = None) -> PasswordResetRequestOut:
    return PasswordResetRequestOut(
        id=req.id,
        user_id=req.user_id,
        username=req.user.username,
        display_name=req.user.display_name,
        status=req.status.value if hasattr(req.status, "value") else str(req.status),
        created_at=req.created_at,
        approved_at=req.approved_at,
        reset_url_token=reset_token,
    )


@router.get("", response_model=list[UserAdminOut])
async def list_users(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserAdminOut]:
    users = await user_service.list_users(db)
    out: list[UserAdminOut] = []
    for user in users:
        usage = await user_service.user_usage_summary(db, user)
        out.append(_admin_out(user, usage))
    return out


@router.get("/password-resets", response_model=list[PasswordResetRequestOut])
async def list_password_resets(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PasswordResetRequestOut]:
    requests = await user_service.list_password_reset_requests(
        db, status=PasswordResetStatus.PENDING
    )
    return [_reset_out(r) for r in requests]


@router.post("/password-resets/{request_id}/approve", response_model=PasswordResetRequestOut)
async def approve_password_reset(
    request_id: uuid.UUID,
    _sess: SafeSession,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PasswordResetRequestOut:
    req, raw = await user_service.approve_password_reset(db, request_id, actor=admin)
    await db.commit()
    return _reset_out(req, reset_token=raw)


@router.post("/password-resets/{request_id}/reject", response_model=MessageOut)
async def reject_password_reset(
    request_id: uuid.UUID,
    _sess: SafeSession,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await user_service.reject_password_reset(db, request_id)
    await db.commit()
    return MessageOut(message="Password reset request rejected")


@router.get("/invites", response_model=list[InviteOut])
async def list_invites(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InviteOut]:
    invites = await user_service.list_invites(db)
    return [InviteOut.model_validate(i) for i in invites]


@router.post("/invites", response_model=InviteOut)
async def create_invite(
    body: InviteCreateRequest,
    _sess: SafeSession,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InviteOut:
    invite, raw = await user_service.create_invite(
        db,
        created_by=admin,
        expires_in_hours=body.expires_in_hours,
        storage_quota_bytes=body.storage_quota_bytes,
        ai_monthly_request_quota=body.ai_monthly_request_quota,
    )
    out = InviteOut.model_validate(invite)
    out.invite_url_token = raw
    return out


@router.delete("/invites/{invite_id}", response_model=MessageOut)
async def revoke_invite(
    invite_id: uuid.UUID,
    _sess: SafeSession,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await user_service.revoke_invite(db, invite_id)
    return MessageOut(message="Invite revoked")


@router.patch("/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    _sess: SafeSession,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserAdminOut:
    storage_q: object = ...
    ai_q: object = ...
    if body.clear_storage_quota:
        storage_q = None
    elif body.storage_quota_bytes is not None:
        storage_q = body.storage_quota_bytes
    if body.clear_ai_quota:
        ai_q = None
    elif body.ai_monthly_request_quota is not None:
        ai_q = body.ai_monthly_request_quota

    user = await user_service.admin_update_user(
        db,
        user_id,
        is_admin=body.is_admin,
        is_active=body.is_active,
        storage_quota_bytes=storage_q,
        ai_monthly_request_quota=ai_q,
        actor=admin,
    )
    usage = await user_service.user_usage_summary(db, user)
    return _admin_out(user, usage)


@router.post("/{user_id}/password", response_model=MessageOut)
async def set_user_password(
    user_id: uuid.UUID,
    body: AdminSetPasswordRequest,
    _sess: SafeSession,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await user_service.admin_set_password(db, user_id, body.password)
    await db.commit()
    return MessageOut(message="Password updated")


@router.delete("/{user_id}", response_model=MessageOut)
async def delete_user(
    user_id: uuid.UUID,
    _sess: SafeSession,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await user_service.delete_user(db, user_id, actor=admin, storage=StorageService())
    return MessageOut(message="User deleted")
