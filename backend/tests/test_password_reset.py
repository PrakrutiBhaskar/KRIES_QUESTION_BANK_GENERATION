"""Forgot-password and reset-password."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import security
from app.config import settings
from app.routers import auth as auth_router

USER = {"name": "Priya Sharma", "email": "priya@school.edu.in", "password": "Sup3rSecret"}


@pytest.fixture
def outbox(monkeypatch):
    """Capture reset emails instead of sending them."""
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        auth_router, "send_password_reset_email", lambda to, name, link: sent.append((to, name, link))
    )
    return sent


def _token(link: str) -> str:
    return re.search(r"token=([^&\s]+)", link).group(1)


async def _register(anon_client):
    r = await anon_client.post("/auth/signup", json=USER)
    assert r.status_code == 201, r.text


async def test_forgot_password_sends_link_for_known_email(anon_client, outbox):
    await _register(anon_client)
    r = await anon_client.post("/auth/forgot-password", json={"email": "  Priya@School.edu.in "})
    assert r.status_code == 200
    assert len(outbox) == 1
    to, name, link = outbox[0]
    assert to == USER["email"] and name == USER["name"]
    assert link.startswith(settings.frontend_url.rstrip("/") + "/reset-password?token=")


async def test_forgot_password_does_not_reveal_unknown_emails(anon_client, outbox):
    await _register(anon_client)
    known = await anon_client.post("/auth/forgot-password", json={"email": USER["email"]})
    unknown = await anon_client.post("/auth/forgot-password", json={"email": "nobody@school.edu.in"})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    assert len(outbox) == 1  # only the real account got a link


async def test_forgot_password_rejects_malformed_email(anon_client, outbox):
    r = await anon_client.post("/auth/forgot-password", json={"email": "nope"})
    assert r.status_code == 400
    assert outbox == []


async def test_reset_password_changes_the_password(anon_client, outbox):
    await _register(anon_client)
    await anon_client.post("/auth/forgot-password", json={"email": USER["email"]})
    token = _token(outbox[0][2])

    r = await anon_client.post("/auth/reset-password", json={"token": token, "password": "BrandNew123"})
    assert r.status_code == 200, r.text

    old = await anon_client.post("/auth/login", json={"email": USER["email"], "password": USER["password"]})
    assert old.status_code == 401
    new = await anon_client.post("/auth/login", json={"email": USER["email"], "password": "BrandNew123"})
    assert new.status_code == 200


async def test_reset_link_is_single_use(anon_client, outbox):
    await _register(anon_client)
    await anon_client.post("/auth/forgot-password", json={"email": USER["email"]})
    token = _token(outbox[0][2])

    assert (await anon_client.post("/auth/reset-password", json={"token": token, "password": "BrandNew123"})).status_code == 200
    again = await anon_client.post("/auth/reset-password", json={"token": token, "password": "Another456"})
    assert again.status_code == 400
    assert again.json()["error"] == "invalid_reset_token"


async def test_reset_rejects_garbage_and_access_tokens(anon_client, outbox):
    signup = await anon_client.post("/auth/signup", json=USER)
    access = signup.json()["access_token"]
    for bad in ("not-a-token", access):
        r = await anon_client.post("/auth/reset-password", json={"token": bad, "password": "BrandNew123"})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_reset_token"


async def test_reset_rejects_expired_token(anon_client, outbox):
    await _register(anon_client)
    await anon_client.post("/auth/forgot-password", json={"email": USER["email"]})
    fresh = outbox[0][2]
    payload = jwt.decode(_token(fresh), options={"verify_signature": False})
    payload["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(payload, security._secret(), algorithm=settings.jwt_algorithm)
    r = await anon_client.post("/auth/reset-password", json={"token": expired, "password": "BrandNew123"})
    assert r.status_code == 400


@pytest.mark.parametrize("password", ["short1", "onlyletters", "12345678"])
async def test_reset_enforces_password_rules(anon_client, outbox, password):
    await _register(anon_client)
    await anon_client.post("/auth/forgot-password", json={"email": USER["email"]})
    r = await anon_client.post(
        "/auth/reset-password", json={"token": _token(outbox[0][2]), "password": password}
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_request"


async def test_forgot_password_is_rate_limited(anon_client, outbox, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_password_reset", "2/60")
    codes = [
        (await anon_client.post("/auth/forgot-password", json={"email": "a@b.co"})).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]
