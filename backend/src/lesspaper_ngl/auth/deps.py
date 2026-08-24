"""FastAPI auth dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.auth import api_tokens as token_service
from lesspaper_ngl.auth import service as auth_service
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.exceptions import AuthError, ForbiddenError
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import Session, User


async def authenticate_request(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Resolve Bearer token first; otherwise the session cookie.

    A present Authorization Bearer header is exclusive: invalid Bearer does
    not fall back to a cookie.
    """
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        user = await token_service.get_user_by_raw_token(db, auth[7:].strip())
        if user is None:
            raise AuthError("Invalid or expired token")
        request.state.auth_via_bearer = True
        request.state.auth_session = None
        return user

    settings = get_settings()
    cookie = request.cookies.get(settings.session_cookie_name)
    if not cookie:
        raise AuthError("Authentication required")
    sess = await auth_service.get_session_by_token(db, cookie)
    if sess is None:
        raise AuthError("Invalid or expired session")
    request.state.auth_via_bearer = False
    request.state.auth_session = sess
    return sess.user


async def get_current_user(
    user: Annotated[User, Depends(authenticate_request)],
) -> User:
    return user


async def get_current_session(
    user: Annotated[User, Depends(authenticate_request)],
    request: Request,
) -> Session:
    del user
    sess = getattr(request.state, "auth_session", None)
    if sess is None:
        raise AuthError("Authentication required")
    return sess


async def require_auth_csrf(
    request: Request,
    user: Annotated[User, Depends(authenticate_request)],
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> Session | None:
    del user
    if getattr(request.state, "auth_via_bearer", False):
        return None
    sess: Session | None = getattr(request.state, "auth_session", None)
    if sess is None:
        raise AuthError("Authentication required")
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return sess
    await auth_service.require_csrf(sess, x_csrf_token)
    return sess


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSession = Annotated[Session, Depends(get_current_session)]
SafeSession = Annotated[Session | None, Depends(require_auth_csrf)]


async def require_admin(
    user: CurrentUser,
) -> User:
    if not user.is_admin:
        raise ForbiddenError("Admin access required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
