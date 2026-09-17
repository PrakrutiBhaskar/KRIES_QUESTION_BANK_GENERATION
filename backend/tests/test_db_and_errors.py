"""
Coverage for the parts of app/db.py, app/errors.py and app/main.py that the
request-level test suite never touches, because the `client` fixture
overrides `get_session` and every request goes through a valid route:

  * db.py    - the real `get_session` dependency (commit-on-success and
               rollback-on-exception), and `build_engine`'s non-sqlite
               (pooled) branch.
  * errors.py - the StarletteHTTPException handler's "already in contract
                shape" branch, and the catch-all handler for a genuinely
                unexpected exception.
  * main.py   - `_redact`, which hides a DB password before it hits the logs.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app import db as db_module
from app.main import _redact, app as fastapi_app

# --- db.py -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_commits_on_clean_exit(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessionmaker_ = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker_)

    gen = db_module.get_session()
    session = await gen.__anext__()
    assert session is not None
    with pytest.raises(StopAsyncIteration):
        # Advancing past the yield runs `await session.commit()`.
        await gen.__anext__()
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_session_rolls_back_and_reraises_on_exception(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessionmaker_ = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker_)

    gen = db_module.get_session()
    await gen.__anext__()
    with pytest.raises(ValueError):
        await gen.athrow(ValueError("boom"))
    await engine.dispose()


def test_build_engine_uses_a_pool_for_non_sqlite_urls():
    engine = db_module.build_engine("postgresql+asyncpg://user:pass@localhost/db")
    # A pooled (non-NullPool) engine is exactly what pool_size/max_overflow
    # configure — this is the signal that the non-sqlite branch ran.
    assert engine.pool.__class__.__name__ != "NullPool"


def test_build_engine_sqlite_does_not_set_a_pool_size():
    # Should not raise even though pool_size/max_overflow are skipped.
    engine = db_module.build_engine("sqlite+aiosqlite:///:memory:")
    assert engine is not None


# --- errors.py ---------------------------------------------------------------


async def _fake_request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/whatever",
        "headers": [],
        "query_string": b"",
    }
    return Request(scope)


async def test_http_exception_handler_passes_through_contract_shaped_detail():
    handler = fastapi_app.exception_handlers[StarletteHTTPException]
    exc = StarletteHTTPException(
        status_code=404,
        detail={"error": "custom_not_found", "detail": "a specific message"},
    )
    response = await handler(await _fake_request(), exc)
    assert response.status_code == 404
    body = json.loads(bytes(response.body))
    assert body == {"error": "custom_not_found", "detail": "a specific message"}


async def test_http_exception_handler_slugifies_a_plain_string_detail():
    handler = fastapi_app.exception_handlers[StarletteHTTPException]
    exc = StarletteHTTPException(status_code=409, detail="already exists")
    response = await handler(await _fake_request(), exc)
    assert response.status_code == 409
    body = json.loads(bytes(response.body))
    assert body == {"error": "conflict", "detail": "already exists"}


async def test_unhandled_exception_handler_returns_the_contract_shape():
    handler = fastapi_app.exception_handlers[Exception]
    response = await handler(await _fake_request(), RuntimeError("something broke"))
    assert response.status_code == 500
    body = json.loads(bytes(response.body))
    assert body == {
        "error": "internal_error",
        "detail": "An unexpected error occurred.",
    }


# --- main.py -----------------------------------------------------------------


def test_redact_hides_the_password():
    url = "postgresql+asyncpg://appuser:s3cret@db.internal:5432/question_bank"
    assert _redact(url) == "postgresql+asyncpg://appuser:***@db.internal:5432/question_bank"


def test_redact_leaves_urls_without_credentials_alone():
    assert _redact("sqlite+aiosqlite:///:memory:") == "sqlite+aiosqlite:///:memory:"


# --- config.py ---------------------------------------------------------------


def test_settings_is_sqlite_property():
    from app.config import Settings

    assert Settings(DATABASE_URL="sqlite+aiosqlite:///:memory:").is_sqlite is True
    assert (
        Settings(DATABASE_URL="postgresql+asyncpg://u:p@h/db").is_sqlite is False
    )


def test_settings_cors_origins_accepts_a_comma_separated_string():
    from app.config import Settings

    settings = Settings(CORS_ORIGINS="http://a.com, http://b.com")
    assert settings.cors_origins == ["http://a.com", "http://b.com"]
