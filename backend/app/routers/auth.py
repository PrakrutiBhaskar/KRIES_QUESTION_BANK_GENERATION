"""
Authentication.

  POST /auth/signup   create an account, returns a token (auto sign-in)
  POST /auth/login    exchange email + password for a token
  GET  /auth/me       the signed-in user, with their saved preferences (also validates a stored token)
  PATCH /auth/me      save profile (name, role) and preference changes; the email can't be changed
  POST /auth/forgot-password   email a password-reset link (same reply whether or not the account exists)
  POST /auth/reset-password    choose a new password using that link
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..models import User
from ..ratelimit import client_ip
from ..schemas import (
    ErrorOut,
    ForgotPasswordIn,
    LoginIn,
    MessageOut,
    ProfileUpdateIn,
    ResetPasswordIn,
    SignUpIn,
    TokenOut,
    UserOut,
)
from ..security import create_access_token
from ..services import auth as auth_service
from ..services.mailer import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenOut:
    token, expires_in = create_access_token(user.id)
    return TokenOut(
        access_token=token, expires_in=expires_in, user=UserOut.model_validate(user)
    )


@router.post(
    "/signup",
    response_model=TokenOut,
    status_code=201,
    summary="Create an account",
    responses={
        400: {"model": ErrorOut},
        409: {"model": ErrorOut},
        429: {"model": ErrorOut},
    },
)
async def signup(body: SignUpIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    user = await auth_service.create_user(
        session,
        name=body.name,
        email=body.email,
        password=body.password,
        role=body.role,
    )
    return _token_response(user)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Sign in",
    responses={401: {"model": ErrorOut}, 429: {"model": ErrorOut}},
)
async def login(
    body: LoginIn, request: Request, session: AsyncSession = Depends(get_session)
) -> TokenOut:
    user = await auth_service.authenticate(
        session, body.email, body.password, client_ip(request.scope)
    )
    return _token_response(user)


@router.post(
    "/forgot-password",
    response_model=MessageOut,
    summary="Email a password-reset link",
    responses={400: {"model": ErrorOut}, 429: {"model": ErrorOut}},
)
async def forgot_password(
    body: ForgotPasswordIn,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> MessageOut:
    # Identical response for known and unknown emails, and the email is sent
    # after the response, so neither the body nor the timing reveals which
    # addresses have an account.
    user = await auth_service.get_by_email(session, body.email)
    if user is not None and user.is_active:
        background.add_task(
            send_password_reset_email,
            user.email,
            user.name,
            auth_service.build_reset_link(user),
        )
    return MessageOut(
        message="If an account exists for that email, a password reset link is on its way."
    )


@router.post(
    "/reset-password",
    response_model=MessageOut,
    summary="Set a new password from a reset link",
    responses={400: {"model": ErrorOut}, 429: {"model": ErrorOut}},
)
async def reset_password(
    body: ResetPasswordIn, session: AsyncSession = Depends(get_session)
) -> MessageOut:
    await auth_service.reset_password(session, body.token, body.password)
    return MessageOut(message="Your password has been updated. You can now sign in.")


@router.get(
    "/me",
    response_model=UserOut,
    summary="Current user",
    responses={401: {"model": ErrorOut}},
)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Update the signed-in user's profile and preferences",
    responses={
        400: {"model": ErrorOut},
        401: {"model": ErrorOut},
        403: {"model": ErrorOut},
    },
)
async def update_me(
    body: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    user = await auth_service.update_profile(session, user, body)
    return UserOut.model_validate(user)
