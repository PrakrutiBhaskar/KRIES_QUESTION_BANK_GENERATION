"""Account creation and credential checks."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import parse_rule, settings
from ..errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    TooManyRequestsError,
    UnauthorizedError,
)
from ..models import User
from ..schemas.auth import PreferencesOut, ProfileUpdateIn
from ..ratelimit import limiter
from ..security import (
    DUMMY_HASH,
    create_reset_token,
    hash_password,
    peek_reset_token,
    reset_token_matches,
    verify_password,
)


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


async def authenticate(
    session: AsyncSession, email: str, password: str, client_ip: str = "unknown"
) -> User:
    # Lockout: too many wrong passwords for this (IP, email) pair blocks it for
    # a while — even if the next password is right — so a password can't be
    # guessed at the per-IP request rate. The email is part of the key, so a
    # stranger can't lock someone out from a different network.
    lock_key = f"login-fail:{client_ip}:{email}"
    lock_rule = parse_rule(settings.login_max_failures)
    if settings.rate_limit_enabled:
        wait = limiter.retry_after(lock_key, lock_rule)
        if wait:
            raise TooManyRequestsError(
                wait,
                detail=(
                    "Too many failed sign-in attempts. "
                    f"Try again in {max(1, round(wait / 60))} minute(s)."
                    if wait >= 60
                    else f"Too many failed sign-in attempts. Try again in {max(1, round(wait))} second(s)."
                ),
            )

    user = await get_by_email(session, email)
    # Always run one scrypt verification, and give one message for both
    # failure modes, so the endpoint doesn't reveal which emails are registered.
    ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not ok or not user.is_active:
        if settings.rate_limit_enabled:
            limiter.record(lock_key, lock_rule)
        raise UnauthorizedError("Incorrect email or password.", error="invalid_credentials")
    limiter.clear(lock_key)
    return user


def build_reset_link(user: User) -> str:
    token = create_reset_token(user.id, user.password_hash)
    return f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"


async def reset_password(session: AsyncSession, token: str, new_password: str) -> User:
    """Set a new password from a reset link. Single-use: the token is bound to the
    old password hash, so it stops working the moment the password changes."""
    invalid = BadRequestError(
        "This reset link is invalid or has expired. Please request a new one.",
        error="invalid_reset_token",
    )
    user_id = peek_reset_token(token)
    if user_id is None:
        raise invalid
    user = await get_by_id(session, user_id)
    if user is None or not user.is_active or not reset_token_matches(token, user.password_hash):
        raise invalid
    user.password_hash = hash_password(new_password)
    await session.flush()
    return user


async def update_profile(
    session: AsyncSession, user: User, changes: ProfileUpdateIn
) -> User:
    """Apply the Settings page's changes and persist them. Only the fields that
    were sent are touched. The email address can never be changed here."""
    if changes.email is not None:
        raise ForbiddenError(
            "Your email address can't be changed.", error="email_immutable"
        )
    if changes.name is not None:
        user.name = changes.name
    if changes.role is not None and changes.role != user.role:
        if user.role == "Admin":
            raise ForbiddenError(
                "An administrator can't change their own role.", error="role_locked"
            )
        user.role = changes.role
    if changes.preferences is not None:
        merged = PreferencesOut.model_validate(user.preferences or {}).model_dump()
        merged.update(changes.preferences.model_dump(exclude_none=True))
        # A fresh dict (not an in-place edit) so SQLAlchemy sees the change.
        user.preferences = PreferencesOut.model_validate(merged).model_dump()
    session.add(user)
    await session.flush()
    return user
