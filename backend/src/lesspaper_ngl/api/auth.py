"""Authentication endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import (
    ApiTokenCreate,
    ApiTokenCreatedOut,
    ApiTokenOut,
    ForgotPasswordOut,
    ForgotPasswordRequest,
    LoginRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    RegistrationStatusOut,
    ResetPasswordRequest,
    ResetPasswordValidateOut,
    SessionOut,
    UserOut,
    UserSessionOut,
    UserUsageOut,
)
from lesspaper_ngl.auth import api_tokens as token_service
from lesspaper_ngl.auth import service as auth_service
from lesspaper_ngl.auth.deps import CurrentSession, CurrentUser, SafeSession
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.exceptions import AuthError, NotFoundError
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import InstanceState, Session, User
from lesspaper_ngl.services import instance_state as instance_state_service
from lesspaper_ngl.services import users as user_service
from lesspaper_ngl.storage.service import StorageService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        storage_quota_bytes=user.storage_quota_bytes,
        ai_monthly_request_quota=user.ai_monthly_request_quota,
        has_avatar=bool(user.avatar_key),
    )


def _use_secure_cookies() -> bool:
    return get_settings().use_secure_cookies


def _cookie_options() -> dict[str, object]:
    settings = get_settings()
    return {
        "httponly": True,
        "secure": _use_secure_cookies(),
        "samesite": "lax",
        "max_age": settings.session_ttl_hours * 3600,
        "path": "/",
    }


def _csrf_cookie_options() -> dict[str, object]:
    settings = get_settings()
    return {
        "httponly": False,
        "secure": _use_secure_cookies(),
        "samesite": "lax",
        "max_age": settings.session_ttl_hours * 3600,
        "path": "/",
    }


def _set_session_cookies(response: Response, raw_token: str, csrf_token: str) -> None:
    settings = get_settings()
    response.set_cookie(settings.session_cookie_name, raw_token, **_cookie_options())
    response.set_cookie(settings.csrf_cookie_name, csrf_token, **_csrf_cookie_options())


def _clear_session_cookies(response: Response) -> None:
    """Expire auth cookies using the same attributes they were set with."""
    settings = get_settings()
    common = {
        "path": "/",
        "secure": _use_secure_cookies(),
        "samesite": "lax",
    }
    response.delete_cookie(
        settings.session_cookie_name,
        httponly=True,
        **common,
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        httponly=False,
        **common,
    )


@router.get("/registration-status", response_model=RegistrationStatusOut)
async def registration_status() -> RegistrationStatusOut:
    return RegistrationStatusOut(allow_registration=get_settings().allow_registration)


@router.post("/register", response_model=SessionOut)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionOut:
    state = await instance_state_service.get_instance_state(db)
    if state == InstanceState.UNINITIALISED:
        raise AuthError("Registration is unavailable until lesspaper-ngl setup completes")
    user = await user_service.register_user(
        db,
        username=body.username,
        password=body.password,
        display_name=body.display_name,
        invite_token=body.invite_token,
    )
    sess, raw_token = await auth_service.create_session(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    # FastAPI runs yield-dependency cleanup after the response is sent; commit
    # before returning so the session cookie is usable on the next request.
    await db.commit()
    _set_session_cookies(response, raw_token, sess.csrf_token)
    return SessionOut(user=user_out(user), csrf_token=sess.csrf_token)


@router.post("/login", response_model=SessionOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionOut:
    rate_key = (request.client.host if request.client else "unknown") + ":" + body.username.lower()
    user_service.check_login_rate_limit(rate_key)
    try:
        user = await auth_service.authenticate(db, body.username, body.password)
    except AuthError:
        user_service.record_login_failure(rate_key)
        raise
    user_service.clear_login_failures(rate_key)
    sess, raw_token = await auth_service.create_session(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    _set_session_cookies(response, raw_token, sess.csrf_token)
    return SessionOut(
        user=user_out(user),
        csrf_token=sess.csrf_token,
    )


@router.post("/logout")
async def logout(
    response: Response,
    sess: CurrentSession,
    _csrf: SafeSession,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    await auth_service.revoke_session(db, sess.id)
    await db.commit()
    _clear_session_cookies(response)
    return {"message": "Logged out"}


@router.get("/me", response_model=SessionOut)
async def me(request: Request, user: CurrentUser) -> SessionOut:
    sess = getattr(request.state, "auth_session", None)
    return SessionOut(
        user=user_out(user),
        csrf_token=sess.csrf_token if sess is not None else "",
    )


@router.post("/tokens", response_model=ApiTokenCreatedOut)
async def create_api_token(
    body: ApiTokenCreate,
    _sess: SafeSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiTokenCreatedOut:
    row, raw = await token_service.create_token(db, user, name=body.name)
    return ApiTokenCreatedOut(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        token=raw,
    )


@router.get("/tokens", response_model=list[ApiTokenOut])
async def list_api_tokens(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApiTokenOut]:
    rows = await token_service.list_tokens(db, user.id)
    return [
        ApiTokenOut(
            id=row.id,
            name=row.name,
            prefix=row.prefix,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
        )
        for row in rows
    ]


@router.delete("/tokens/{token_id}", response_model=ForgotPasswordOut)
async def revoke_api_token(
    token_id: uuid.UUID,
    _sess: SafeSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ForgotPasswordOut:
    await token_service.delete_token(db, token_id, user_id=user.id)
    return ForgotPasswordOut(message="Token revoked")


@router.get("/me/sessions", response_model=list[UserSessionOut])
async def list_my_sessions(
    sess: CurrentSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserSessionOut]:
    rows = (
        (
            await db.execute(
                select(Session)
                .where(Session.user_id == user.id)
                .order_by(Session.last_seen_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        UserSessionOut(
            id=row.id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            current=row.id == sess.id,
        )
        for row in rows
    ]


@router.delete("/me/sessions/{session_id}", response_model=ForgotPasswordOut)
async def revoke_my_session(
    session_id: uuid.UUID,
    response: Response,
    sess: CurrentSession,
    _csrf: SafeSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ForgotPasswordOut:
    target = await db.get(Session, session_id)
    if target is None or target.user_id != user.id:
        raise NotFoundError("Session not found")
    await db.delete(target)
    if session_id == sess.id:
        _clear_session_cookies(response)
    return ForgotPasswordOut(message="Session signed out")


@router.post("/me/sessions/sign-out-others", response_model=ForgotPasswordOut)
async def sign_out_other_sessions(
    sess: CurrentSession,
    _csrf: SafeSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ForgotPasswordOut:
    await db.execute(delete(Session).where(Session.user_id == user.id, Session.id != sess.id))
    return ForgotPasswordOut(message="Other sessions signed out")


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: ProfileUpdateRequest,
    _sess: SafeSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    updated = await user_service.update_profile(
        db,
        user,
        display_name=body.display_name,
        username=body.username,
    )
    return user_out(updated)


@router.post("/me/password")
async def change_my_password(
    body: PasswordChangeRequest,
    response: Response,
    sess: SafeSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    await user_service.change_password(
        db,
        user,
        current_password=body.current_password,
        new_password=body.new_password,
        keep_session_id=None,
    )
    await db.commit()
    _clear_session_cookies(response)
    return {"message": "Password updated. Please sign in again."}


@router.get("/me/usage", response_model=UserUsageOut)
async def my_usage(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserUsageOut:
    return UserUsageOut(**await user_service.user_usage_summary(db, user))


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    _sess: SafeSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> UserOut:
    data = await file.read()
    updated = await user_service.set_avatar(
        db,
        user,
        data=data,
        content_type=file.content_type,
        storage=StorageService(),
    )
    await db.commit()
    return user_out(updated)


@router.delete("/me/avatar", response_model=UserOut)
async def delete_avatar(
    _sess: SafeSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    updated = await user_service.clear_avatar(db, user, storage=StorageService())
    await db.commit()
    return user_out(updated)


@router.get("/me/avatar")
async def get_my_avatar(user: CurrentUser) -> FileResponse:
    if not user.avatar_key:
        raise NotFoundError("No avatar set")
    path = StorageService().open_avatar_path(user.avatar_key)
    return FileResponse(path, media_type="image/webp", filename="avatar.webp")


@router.post("/forgot-password", response_model=ForgotPasswordOut)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ForgotPasswordOut:
    rate_key = (request.client.host if request.client else "unknown") + ":" + body.username.lower()
    user_service.check_forgot_rate_limit(rate_key)
    message = await user_service.request_password_reset(db, username=body.username)
    await db.commit()
    return ForgotPasswordOut(message=message)


@router.get("/reset-password/validate", response_model=ResetPasswordValidateOut)
async def validate_reset_password(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ResetPasswordValidateOut:
    valid, user = await user_service.validate_reset_token(db, token)
    return ResetPasswordValidateOut(
        valid=valid,
        username=user.username if user else None,
    )


@router.post("/reset-password", response_model=ForgotPasswordOut)
async def reset_password(
    body: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ForgotPasswordOut:
    await user_service.complete_password_reset(db, token=body.token, new_password=body.new_password)
    await db.commit()
    return ForgotPasswordOut(message="Password updated. You can sign in with your new password.")
