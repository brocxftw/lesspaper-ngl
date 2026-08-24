"""Personal API tokens (hashed secrets, shown once)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lesspaper_ngl.auth.passwords import generate_token, hash_token
from lesspaper_ngl.core.exceptions import NotFoundError, ValidationError
from lesspaper_ngl.models import ApiToken, User

_TOKEN_PREFIX = "fol_"
_DISPLAY_PREFIX_LEN = 12


def _new_raw_token() -> str:
    return _TOKEN_PREFIX + generate_token(32)


async def create_token(session: AsyncSession, user: User, *, name: str) -> tuple[ApiToken, str]:
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Token name is required")
    raw = _new_raw_token()
    row = ApiToken(
        user_id=user.id,
        name=cleaned,
        token_hash=hash_token(raw),
        prefix=raw[:_DISPLAY_PREFIX_LEN],
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row, raw


async def list_tokens(session: AsyncSession, user_id: UUID) -> list[ApiToken]:
    result = await session.execute(
        select(ApiToken)
        .where(ApiToken.user_id == user_id)
        .order_by(ApiToken.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_token(session: AsyncSession, token_id: UUID, *, user_id: UUID) -> None:
    row = await session.get(ApiToken, token_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError("Token not found")
    await session.delete(row)


async def get_user_by_raw_token(session: AsyncSession, raw_token: str) -> User | None:
    if not raw_token:
        return None
    row = (
        await session.execute(
            select(ApiToken)
            .options(selectinload(ApiToken.user))
            .where(ApiToken.token_hash == hash_token(raw_token))
        )
    ).scalar_one_or_none()
    if row is None or not row.user.is_active:
        return None
    row.last_used_at = datetime.now(UTC)
    return row.user
