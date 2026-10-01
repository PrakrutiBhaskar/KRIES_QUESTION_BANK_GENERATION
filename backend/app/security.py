"""
Password hashing and access tokens.

* Passwords: scrypt from the standard library (memory-hard, no extra
  dependency). Stored as ``scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>`` so the
  cost parameters can be raised later without invalidating old hashes.
* Tokens: short JSON Web Tokens signed with HS256 (PyJWT). The subject is the
  user's id; nothing else sensitive goes in the token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

logger = logging.getLogger("backend.security")

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32

# Used when JWT_SECRET is unset. Generated once per process.
_EPHEMERAL_SECRET = secrets.token_urlsafe(48)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_BYTES,
        maxmem=64 * 1024 * 1024,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check. Returns False (never raises) on a malformed hash."""
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(key_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=64 * 1024 * 1024,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# A valid hash of a random password, verified against when the email is
# unknown so "no such user" and "wrong password" take about the same time.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _secret() -> str:
    return _EPHEMERAL_SECRET if settings.jwt_secret_is_ephemeral else settings.jwt_secret


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """Return (token, lifetime_in_seconds)."""
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + lifetime},
        _secret(),
        algorithm=settings.jwt_algorithm,
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> uuid.UUID | None:
    """The user id in a valid, unexpired token — otherwise None."""
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        return uuid.UUID(str(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


# --- Short-lived download links ---------------------------------------------
# A browser tab opened with window.open() can't send an Authorization header,
# so POST /export/{id} (which IS authenticated and owner-checked) returns a
# link carrying a signed token bound to that one filename. The token has no
# "sub" claim, so it can never be used as an access token, and vice versa.

DOWNLOAD_TOKEN_TTL_SECONDS = 10 * 60


def create_download_token(filename: str, ttl_seconds: int = DOWNLOAD_TOKEN_TTL_SECONDS) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"typ": "download", "fn": filename, "iat": now, "exp": now + timedelta(seconds=ttl_seconds)},
        _secret(),
        algorithm=settings.jwt_algorithm,
    )


def verify_download_token(token: str, filename: str) -> bool:
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "fn", "typ"]},
        )
    except jwt.PyJWTError:
        return False
    return payload.get("typ") == "download" and hmac.compare_digest(
        str(payload.get("fn")), filename
    )

# --- Password-reset tokens ---------------------------------------------------
# Stateless (no table needed). The token carries a fingerprint of the user's
# CURRENT password hash, so once the password is changed the same link stops
# working: reset links are single-use without storing anything.


def _pw_fingerprint(password_hash: str) -> str:
    return hmac.new(
        _secret().encode("utf-8"), password_hash.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:24]


def create_reset_token(user_id: uuid.UUID, password_hash: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "typ": "reset",
            "sub": str(user_id),
            "pw": _pw_fingerprint(password_hash),
            "iat": now,
            "exp": now + timedelta(minutes=settings.password_reset_expire_minutes),
        },
        _secret(),
        algorithm=settings.jwt_algorithm,
    )


def peek_reset_token(token: str) -> uuid.UUID | None:
    """The user id inside a well-formed, unexpired reset token, else None.
    Says nothing about whether the link was already used; see reset_token_matches."""
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "typ", "pw"]},
        )
        if payload.get("typ") != "reset":
            return None
        return uuid.UUID(str(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def reset_token_matches(token: str, password_hash: str) -> bool:
    """True if the token was issued against this exact password hash."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return False
    return hmac.compare_digest(str(payload.get("pw", "")), _pw_fingerprint(password_hash))
