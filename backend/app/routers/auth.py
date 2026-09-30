"""
Authentication.

  POST /auth/signup   create an account, returns a token (auto sign-in)
  POST /auth/login    exchange email + password for a token
  GET  /auth/me       the signed-in user (also validates a stored token)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..models import User
from ..schemas import ErrorOut, LoginIn, SignUpIn, TokenOut, UserOut
from ..security import create_access_token
from ..services import auth as auth_service

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
    responses={400: {"model": ErrorOut}, 409: {"model": ErrorOut}},
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
    responses={401: {"model": ErrorOut}},
)
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    user = await auth_service.authenticate(session, body.email, body.password)
    return _token_response(user)


@router.get(
    "/me",
    response_model=UserOut,
    summary="Current user",
    responses={401: {"model": ErrorOut}},
)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
