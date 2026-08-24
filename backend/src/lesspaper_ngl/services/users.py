"""User registration, profile, invites, avatars, and admin user management."""

from __future__ import annotations

import io
import re
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lesspaper_ngl.auth.passwords import generate_token, hash_password, hash_token, verify_password
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.exceptions import (
    AuthError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from lesspaper_ngl.models import (
    Document,
    Folder,
    Invite,
    PasswordResetRequest,
    PasswordResetStatus,
    Session,
    User,
)
from lesspaper_ngl.services import folders as folder_service
from lesspaper_ngl.services import quotas as quota_service
from lesspaper_ngl.storage.service import StorageService

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
_login_attempts: dict[str, list[float]] = defaultdict(list)
_forgot_attempts: dict[str, list[float]] = defaultdict(list)
_AVATAR_MIME = {"image/jpeg", "image/png", "image/webp"}
_AVATAR_SIZE = 256

_NEUTRAL_FORGOT_MSG = (
    "If that account exists, an admin has been notified. "
    "They will share a reset link with you when approved."
)


def _validate_username(username: str) -> str:
    username = username.strip()
    if not _USERNAME_RE.match(username):
        raise ValidationError(
            "Username must be 3–32 characters and contain only letters, numbers, and underscores"
        )
    return username


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters")


def check_login_rate_limit(
    key: str, *, max_attempts: int = 10, window_seconds: float = 300
) -> None:
    now = time.monotonic()
    window = [t for t in _login_attempts[key] if now - t < window_seconds]
    _login_attempts[key] = window
    if len(window) >= max_attempts:
        raise AuthError("Too many login attempts. Try again later.")


def record_login_failure(key: str) -> None:
    _login_attempts[key].append(time.monotonic())


def clear_login_failures(key: str) -> None:
    _login_attempts.pop(key, None)


def check_forgot_rate_limit(
    key: str, *, max_attempts: int = 5, window_seconds: float = 300
) -> None:
    now = time.monotonic()
    window = [t for t in _forgot_attempts[key] if now - t < window_seconds]
    _forgot_attempts[key] = window
    if len(window) >= max_attempts:
        raise AuthError("Too many password reset requests. Try again later.")
    _forgot_attempts[key].append(now)


async def register_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    display_name: str,
    invite_token: str | None = None,
) -> User:
    settings = get_settings()
    username = _validate_username(username)
    _validate_password(password)
    display_name = display_name.strip() or username

    invite: Invite | None = None
    if invite_token:
        invite = await get_valid_invite(session, invite_token)
    elif not settings.allow_registration:
        raise ForbiddenError("Registration is disabled")

    existing = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("Username is already taken")

    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        is_admin=False,
        is_active=True,
        storage_quota_bytes=invite.storage_quota_bytes
        if invite
        else settings.default_storage_quota_bytes,
        ai_monthly_request_quota=(
            invite.ai_monthly_request_quota if invite else settings.default_ai_monthly_request_quota
        ),
    )
    session.add(user)
    await session.flush()
    await folder_service.ensure_system_folders(session, user.id)

    if invite is not None:
        invite.used_at = datetime.now(UTC)
        invite.used_by_id = user.id
        await session.flush()

    return user


async def update_profile(
    session: AsyncSession,
    user: User,
    *,
    display_name: str | None = None,
    username: str | None = None,
) -> User:
    if display_name is not None:
        name = display_name.strip()
        if not name:
            raise ValidationError("Display name is required")
        user.display_name = name
    if username is not None:
        username = _validate_username(username)
        if username != user.username:
            conflict = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if conflict:
                raise ConflictError("Username is already taken")
            user.username = username
    await session.flush()
    return user


async def change_password(
    session: AsyncSession,
    user: User,
    *,
    current_password: str,
    new_password: str,
    keep_session_id: uuid.UUID | None = None,
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise AuthError("Current password is incorrect")
    _validate_password(new_password)
    user.password_hash = hash_password(new_password)
    await session.flush()
    stmt = delete(Session).where(Session.user_id == user.id)
    if keep_session_id is not None:
        stmt = stmt.where(Session.id != keep_session_id)
    await session.execute(stmt)


def _process_avatar_image(data: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGBA")
    except Exception as exc:
        raise ValidationError("Invalid image file") from exc

    width, height = img.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((_AVATAR_SIZE, _AVATAR_SIZE), Image.Resampling.LANCZOS)

    background = Image.new("RGB", img.size, (255, 255, 255))
    background.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
    out = io.BytesIO()
    background.save(out, format="WEBP", quality=85)
    return out.getvalue()


async def set_avatar(
    session: AsyncSession,
    user: User,
    *,
    data: bytes,
    content_type: str | None,
    storage: StorageService | None = None,
) -> User:
    settings = get_settings()
    if len(data) > settings.max_avatar_bytes:
        raise ValidationError(f"Avatar must be at most {settings.max_avatar_size_mb} MB")
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype not in _AVATAR_MIME:
        raise ValidationError("Avatar must be a JPEG, PNG, or WebP image")

    processed = _process_avatar_image(data)
    storage = storage or StorageService()
    old_key = user.avatar_key
    key = await storage.persist_avatar(processed, user_id=str(user.id))
    user.avatar_key = key
    await session.flush()
    if old_key and old_key != key:
        await storage.delete_avatar(old_key)
    return user


async def clear_avatar(
    session: AsyncSession,
    user: User,
    *,
    storage: StorageService | None = None,
) -> User:
    storage = storage or StorageService()
    old_key = user.avatar_key
    user.avatar_key = None
    await session.flush()
    await storage.delete_avatar(old_key)
    return user


async def list_users(session: AsyncSession) -> list[User]:
    return list(
        (await session.execute(select(User).order_by(User.created_at.asc()))).scalars().all()
    )


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


async def admin_update_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    is_admin: bool | None = None,
    is_active: bool | None = None,
    storage_quota_bytes: int | None | object = ...,
    ai_monthly_request_quota: int | None | object = ...,
    actor: User,
) -> User:
    user = await get_user(session, user_id)
    if is_admin is not None and user.is_admin and not is_admin:
        admins = (
            await session.execute(
                select(func.count())
                .select_from(User)
                .where(User.is_admin.is_(True), User.is_active.is_(True))
            )
        ).scalar_one()
        if admins <= 1:
            raise ValidationError("Cannot demote the last admin")
        if user.id == actor.id:
            raise ValidationError("Cannot demote yourself")
    if is_admin is not None:
        user.is_admin = is_admin
    if is_active is not None:
        if user.id == actor.id and not is_active:
            raise ValidationError("Cannot deactivate yourself")
        user.is_active = is_active
        if not is_active:
            await session.execute(delete(Session).where(Session.user_id == user.id))
    if storage_quota_bytes is not ... or ai_monthly_request_quota is not ...:
        if user.id == actor.id:
            raise ValidationError("Cannot change your own storage or AI quotas")
    if storage_quota_bytes is not ...:
        user.storage_quota_bytes = storage_quota_bytes  # type: ignore[assignment]
    if ai_monthly_request_quota is not ...:
        user.ai_monthly_request_quota = ai_monthly_request_quota  # type: ignore[assignment]
    await session.flush()
    return user


async def admin_set_password(session: AsyncSession, user_id: uuid.UUID, password: str) -> User:
    user = await get_user(session, user_id)
    _validate_password(password)
    user.password_hash = hash_password(password)
    await session.execute(delete(Session).where(Session.user_id == user.id))
    await session.flush()
    return user


async def resolve_admin_user(
    session: AsyncSession, *, username: str | None = None
) -> User:
    """Resolve an admin for ops (CLI recovery, consume ownership).

    Prefer an explicit username when given; otherwise the earliest active admin.
    """
    if username:
        user = (
            await session.execute(select(User).where(User.username == username.strip()))
        ).scalar_one_or_none()
        if user is None:
            raise NotFoundError(f"User @{username} not found")
        if not user.is_active:
            raise ValidationError(f"User @{username} is inactive")
        return user

    admin = (
        await session.execute(
            select(User)
            .where(User.is_admin.is_(True), User.is_active.is_(True))
            .order_by(User.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if admin is None:
        raise NotFoundError("No active admin user found")
    return admin


async def resolve_consume_owner(session: AsyncSession) -> User:
    """Owner for consume-folder ingest: CONSUME_OWNER_USERNAME or earliest admin."""
    settings = get_settings()
    preferred = (settings.consume_owner_username or "").strip() or None
    if preferred:
        return await resolve_admin_user(session, username=preferred)
    return await resolve_admin_user(session, username=None)


async def delete_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    actor: User,
    storage: StorageService | None = None,
) -> None:
    from lesspaper_ngl.services import documents as doc_service

    user = await get_user(session, user_id)
    if user.id == actor.id:
        raise ValidationError("Cannot delete yourself")
    if user.is_admin:
        admins = (
            await session.execute(
                select(func.count()).select_from(User).where(User.is_admin.is_(True))
            )
        ).scalar_one()
        if admins <= 1:
            raise ValidationError("Cannot delete the last admin")

    storage = storage or StorageService()
    await storage.delete_avatar(user.avatar_key)
    doc_ids = (
        (await session.execute(select(Document.id).where(Document.owner_id == user.id)))
        .scalars()
        .all()
    )
    for doc_id in doc_ids:
        doc = await session.get(Document, doc_id)
        if doc is None:
            continue
        doc.is_trashed = True
        await session.flush()
        await doc_service.permanently_delete(
            session,
            doc_id,
            owner_id=user.id,
            storage=storage,
        )

    await session.execute(delete(Folder).where(Folder.owner_id == user.id))
    await session.delete(user)
    await session.flush()


async def create_invite(
    session: AsyncSession,
    *,
    created_by: User,
    expires_in_hours: int = 168,
    storage_quota_bytes: int | None = None,
    ai_monthly_request_quota: int | None = None,
) -> tuple[Invite, str]:
    raw = generate_token(24)
    invite = Invite(
        token_hash=hash_token(raw),
        created_by_id=created_by.id,
        expires_at=datetime.now(UTC) + timedelta(hours=expires_in_hours),
        storage_quota_bytes=storage_quota_bytes,
        ai_monthly_request_quota=ai_monthly_request_quota,
    )
    session.add(invite)
    await session.flush()
    return invite, raw


async def list_invites(session: AsyncSession) -> list[Invite]:
    return list(
        (await session.execute(select(Invite).order_by(Invite.created_at.desc()).limit(100)))
        .scalars()
        .all()
    )


async def get_valid_invite(session: AsyncSession, raw_token: str) -> Invite:
    invite = (
        await session.execute(select(Invite).where(Invite.token_hash == hash_token(raw_token)))
    ).scalar_one_or_none()
    if invite is None:
        raise NotFoundError("Invite not found")
    if invite.used_at is not None:
        raise ValidationError("Invite has already been used")
    if invite.expires_at < datetime.now(UTC):
        raise ValidationError("Invite has expired")
    return invite


async def revoke_invite(session: AsyncSession, invite_id: uuid.UUID) -> None:
    invite = await session.get(Invite, invite_id)
    if invite is None:
        raise NotFoundError("Invite not found")
    if invite.used_at is not None:
        raise ValidationError("Invite already used")
    await session.delete(invite)
    await session.flush()


async def user_usage_summary(session: AsyncSession, user: User) -> dict:
    storage_used = await quota_service.storage_usage_bytes(session, user.id)
    ai_used = await quota_service.ai_requests_this_month(session, user.id)
    return {
        "storage_used_bytes": storage_used,
        "storage_quota_bytes": user.storage_quota_bytes,
        "ai_requests_this_month": ai_used,
        "ai_monthly_request_quota": user.ai_monthly_request_quota,
    }


async def request_password_reset(session: AsyncSession, *, username: str) -> str:
    """Create or refresh a pending reset request. Always returns a neutral message."""
    username = username.strip()
    user = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return _NEUTRAL_FORGOT_MSG

    existing = (
        await session.execute(
            select(PasswordResetRequest).where(
                PasswordResetRequest.user_id == user.id,
                PasswordResetRequest.status == PasswordResetStatus.PENDING,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.updated_at = datetime.now(UTC)
        await session.flush()
        return _NEUTRAL_FORGOT_MSG

    req = PasswordResetRequest(
        user_id=user.id,
        status=PasswordResetStatus.PENDING,
    )
    session.add(req)
    await session.flush()
    return _NEUTRAL_FORGOT_MSG


async def list_password_reset_requests(
    session: AsyncSession, *, status: PasswordResetStatus | None = PasswordResetStatus.PENDING
) -> list[PasswordResetRequest]:
    stmt = (
        select(PasswordResetRequest)
        .options(selectinload(PasswordResetRequest.user))
        .order_by(PasswordResetRequest.created_at.desc())
    )
    if status is not None:
        stmt = stmt.where(PasswordResetRequest.status == status)
    return list((await session.execute(stmt.limit(100))).scalars().all())


async def approve_password_reset(
    session: AsyncSession,
    request_id: uuid.UUID,
    *,
    actor: User,
) -> tuple[PasswordResetRequest, str]:
    req = (
        await session.execute(
            select(PasswordResetRequest)
            .options(selectinload(PasswordResetRequest.user))
            .where(PasswordResetRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if req is None:
        raise NotFoundError("Password reset request not found")
    if req.status != PasswordResetStatus.PENDING:
        raise ValidationError("Request is not pending")

    settings = get_settings()
    raw = generate_token(32)
    now = datetime.now(UTC)
    req.status = PasswordResetStatus.APPROVED
    req.reset_token_hash = hash_token(raw)
    req.reset_token_expires_at = now + timedelta(hours=settings.password_reset_token_ttl_hours)
    req.approved_by_id = actor.id
    req.approved_at = now
    await session.flush()
    return req, raw


async def reject_password_reset(session: AsyncSession, request_id: uuid.UUID) -> PasswordResetRequest:
    req = await session.get(PasswordResetRequest, request_id)
    if req is None:
        raise NotFoundError("Password reset request not found")
    if req.status != PasswordResetStatus.PENDING:
        raise ValidationError("Request is not pending")
    req.status = PasswordResetStatus.REJECTED
    req.rejected_at = datetime.now(UTC)
    await session.flush()
    return req


async def validate_reset_token(
    session: AsyncSession, raw_token: str
) -> tuple[bool, User | None]:
    req = await _get_usable_reset_request(session, raw_token)
    if req is None:
        return False, None
    return True, req.user


async def complete_password_reset(
    session: AsyncSession, *, token: str, new_password: str
) -> User:
    req = await _get_usable_reset_request(session, token)
    if req is None:
        raise ValidationError("Reset link is invalid or has expired")
    _validate_password(new_password)
    user = req.user
    user.password_hash = hash_password(new_password)
    req.status = PasswordResetStatus.USED
    req.used_at = datetime.now(UTC)
    await session.execute(delete(Session).where(Session.user_id == user.id))
    await session.flush()
    return user


async def _get_usable_reset_request(
    session: AsyncSession, raw_token: str
) -> PasswordResetRequest | None:
    if not raw_token:
        return None
    req = (
        await session.execute(
            select(PasswordResetRequest)
            .options(selectinload(PasswordResetRequest.user))
            .where(PasswordResetRequest.reset_token_hash == hash_token(raw_token))
        )
    ).scalar_one_or_none()
    if req is None:
        return None
    if req.status != PasswordResetStatus.APPROVED:
        return None
    if req.reset_token_expires_at is None or req.reset_token_expires_at < datetime.now(UTC):
        if req.status == PasswordResetStatus.APPROVED:
            req.status = PasswordResetStatus.EXPIRED
            await session.flush()
        return None
    if req.user is None or not req.user.is_active:
        return None
    return req
