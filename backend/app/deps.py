"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .errors import ForbiddenError, UnauthorizedError
from .models import User
from .security import decode_access_token
from .services import auth as auth_service

# auto_error=False so a missing header goes through our {"error","detail"} shape
# instead of FastAPI's default 403 body.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the signed-in user from `Authorization: Bearer <token>`.

    Not yet attached to the existing question/paper routes — add
    ``user: User = Depends(get_current_user)`` to any route that should
    require sign-in.
    """
    if credentials is None:
        raise UnauthorizedError("Not signed in.", error="not_authenticated")
    user_id = decode_access_token(credentials.credentials)
    user = await auth_service.get_by_id(session, user_id) if user_id else None
    if user is None or not user.is_active:
        raise UnauthorizedError(
            "Your session is invalid or has expired. Please sign in again.",
            error="invalid_token",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Gate for admin-only actions (managing the shared figure library).

    The role lives on the account (`users.role == "Admin"`). It can't be chosen
    at sign-up or changed through PATCH /auth/me; an administrator is made on the
    server with `scripts/make_admin.py`.
    """
    if user.role != "Admin":
        raise ForbiddenError(
            "Only administrators can change the figure library.",
            error="admin_required",
        )
    return user
