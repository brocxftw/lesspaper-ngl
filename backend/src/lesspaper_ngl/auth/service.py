"""Authentication and session management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lesspaper_ngl.auth.passwords import generate_token, hash_password, hash_token, verify_password
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.exceptions import AuthError, ForbiddenError, ValidationError
from lesspaper_ngl.models import Session, User


async def ensure_admin_user(session: AsyncSession) -> User:
    """Ensure an admin exists for bootstrap.

    - If ``LESSPAPER_NGL_ADMIN_USERNAME`` exists, return that user.
    - If the database is empty, create the configured bootstrap admin.
    - If users already exist under a different username (common after rename),
      return the earliest active admin so startup does not crash.
    """
    settings = get_settings()
    user = (
        await session.execute(select(User).where(User.username == settings.admin_username))
    ).scalar_one_or_none()
    if user is not None:
        return user

    any_user = (await session.execute(select(User).limit(1))).scalar_one_or_none()
    if any_user is None:
        user = User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            display_name="Local Admin",
            is_admin=True,
        )
        session.add(user)
        await session.flush()
        from lesspaper_ngl.services import folders as folder_service

        await folder_service.ensure_system_folders(session, user.id)
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
        raise ValidationError(
            "No active admin user found. Create an admin account or set "
            "LESSPAPER_NGL_ADMIN_USERNAME to an existing admin username."
        )
    return admin



async def authenticate(
    session: AsyncSession, username: str, password: str
) -> User:
    user = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        raise AuthError("Invalid username or password")
    return user


async def create_session(
    session: AsyncSession,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[Session, str]:
    settings = get_settings()
    raw_token = generate_token(32)
    csrf = generate_token(24)
    row = Session(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        csrf_token=csrf,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.add(row)
    await session.flush()
    return row, raw_token


async def get_session_by_token(session: AsyncSession, raw_token: str) -> Session | None:
    token_hash = hash_token(raw_token)
    row = (
        await session.execute(
            select(Session)
            .options(selectinload(Session.user))
            .where(Session.token_hash == token_hash)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.expires_at < datetime.now(UTC):
        await session.delete(row)
        return None
    if not row.user.is_active:
        return None
    row.last_seen_at = datetime.now(UTC)
    return row


async def revoke_session(session: AsyncSession, session_id: UUID) -> None:
    await session.execute(delete(Session).where(Session.id == session_id))


async def require_csrf(sess: Session, csrf_header: str | None) -> None:
    if not csrf_header or csrf_header != sess.csrf_token:
        raise ForbiddenError("CSRF token missing or invalid")
