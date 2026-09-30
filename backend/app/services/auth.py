"""Account creation and credential checks."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ConflictError, UnauthorizedError
from ..models import User
from ..security import DUMMY_HASH, hash_password, verify_password


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def create_user(
    session: AsyncSession, *, name: str, email: str, password: str, role: str
) -> User:
    if await get_by_email(session, email) is not None:
        raise ConflictError(
            "An account with this email already exists.", error="email_taken"
        )
    user = User(name=name, email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        # Two sign-ups racing past the check above: the unique index decides.
        await session.rollback()
        raise ConflictError(
            "An account with this email already exists.", error="email_taken"
        )
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await get_by_email(session, email)
    # Always run one scrypt verification, and give one message for both
    # failure modes, so the endpoint doesn't reveal which emails are registered.
    ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not ok or not user.is_active:
        raise UnauthorizedError("Incorrect email or password.", error="invalid_credentials")
    return user
