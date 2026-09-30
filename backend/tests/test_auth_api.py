"""Sign-up, sign-in and /auth/me."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import security
from app.config import settings

VALID = {"name": "Priya Sharma", "email": "priya@school.edu.in", "password": "Sup3rSecret"}


async def _signup(client, **overrides):
    return await client.post("/auth/signup", json={**VALID, **overrides})


async def test_signup_returns_token_and_user(client):
    r = await _signup(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_expire_minutes * 60
    assert body["user"]["email"] == "priya@school.edu.in"
    assert body["user"]["role"] == "Teacher"
    assert "password" not in body["user"] and "password_hash" not in body["user"]


async def test_signup_token_works_on_me(client):
    token = (await _signup(client)).json()["access_token"]
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["name"] == "Priya Sharma"


async def test_signup_normalises_email_and_name(client):
    r = await _signup(client, email="  Priya@School.EDU.in ", name="  Priya   Sharma ")
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "priya@school.edu.in"
    assert r.json()["user"]["name"] == "Priya Sharma"


async def test_duplicate_email_is_409_case_insensitive(client):
    assert (await _signup(client)).status_code == 201
    r = await _signup(client, email="PRIYA@school.edu.in")
    assert r.status_code == 409
    assert r.json()["error"] == "email_taken"


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short1"},  # too short
        {"password": "onlyletters"},  # no digit
        {"password": "12345678"},  # no letter
        {"email": "not-an-email"},
        {"name": "   "},
        {"role": "Admin"},  # cannot self-assign
    ],
)
async def test_signup_validation_errors_use_contract_shape(client, overrides):
    r = await _signup(client, **overrides)
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_request"
    assert r.json()["detail"]


async def test_student_role_allowed(client):
    r = await _signup(client, role="Student")
    assert r.json()["user"]["role"] == "Student"


async def test_password_is_hashed_at_rest(client, db_session):
    from sqlalchemy import select

    from app.models import User

    await _signup(client)
    row = (await db_session.execute(select(User))).scalar_one()
    assert row.password_hash != VALID["password"]
    assert row.password_hash.startswith("scrypt$")


async def test_login_success(client):
    await _signup(client)
    r = await client.post(
        "/auth/login", json={"email": "PRIYA@school.edu.in", "password": VALID["password"]}
    )
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_login_wrong_password_and_unknown_email_look_identical(client):
    await _signup(client)
    wrong = await client.post(
        "/auth/login", json={"email": VALID["email"], "password": "Wrong-pass1"}
    )
    unknown = await client.post(
        "/auth/login", json={"email": "nobody@school.edu.in", "password": "Wrong-pass1"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"] == "invalid_credentials"


async def test_me_requires_a_token(client):
    r = await client.get("/auth/me")
    assert r.status_code == 401
    assert r.json()["error"] == "not_authenticated"


async def test_me_rejects_garbage_token(client):
    r = await client.get("/auth/me", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_token"


async def test_me_rejects_expired_token(client):
    user_id = uuid.UUID((await _signup(client)).json()["user"]["id"])
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired = jwt.encode(
        {"sub": str(user_id), "iat": past - timedelta(hours=1), "exp": past},
        security._secret(),
        algorithm=settings.jwt_algorithm,
    )
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


async def test_me_rejects_token_signed_with_another_key(client):
    user_id = (await _signup(client)).json()["user"]["id"]
    forged = jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "some-other-secret-key-that-is-long-enough-1234",
        algorithm="HS256",
    )
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


async def test_me_rejects_token_for_deleted_user(client):
    token = security.create_access_token(uuid.uuid4())[0]
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_password_hash_roundtrip_and_malformed_hash():
    h = security.hash_password("Correct-horse9")
    assert security.verify_password("Correct-horse9", h)
    assert not security.verify_password("Correct-horse8", h)
    assert not security.verify_password("x", "garbage")
    assert security.hash_password("Correct-horse9") != h  # per-hash salt
