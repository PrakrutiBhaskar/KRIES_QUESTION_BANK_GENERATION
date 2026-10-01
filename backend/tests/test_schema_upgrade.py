"""Upgrading a database created before ownership existed."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import Base, ensure_schema

BACKEND_ROOT = Path(__file__).resolve().parents[1]


async def _columns(engine, table):
    async with engine.connect() as conn:
        return await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns(table)}
        )


async def _indexes(engine, table):
    async with engine.connect() as conn:
        return await conn.run_sync(
            lambda c: {i["name"] for i in inspect(c).get_indexes(table)}
        )


async def test_ensure_schema_adds_the_new_column_and_indexes_to_an_old_database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Turn it back into what a pre-ownership database looked like.
        for index in ("ix_questions_created_by", "ix_papers_user_id", "ix_practice_sessions_user_id"):
            await conn.execute(text(f"DROP INDEX {index}"))
        await conn.execute(text("ALTER TABLE questions DROP COLUMN created_by"))
    assert "created_by" not in await _columns(engine, "questions")

    async with engine.begin() as conn:
        await conn.run_sync(ensure_schema)

    assert "created_by" in await _columns(engine, "questions")
    assert "ix_questions_created_by" in await _indexes(engine, "questions")
    assert "ix_papers_user_id" in await _indexes(engine, "papers")
    assert "ix_practice_sessions_user_id" in await _indexes(engine, "practice_sessions")

    # Safe to run on every startup.
    async with engine.begin() as conn:
        await conn.run_sync(ensure_schema)
    await engine.dispose()


def test_alembic_migrations_run_to_head_and_back(tmp_path):
    db = tmp_path / "migrated.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db}"}

    def alembic(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_ROOT, env=env, capture_output=True, text=True,
        )

    up = alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    import sqlite3

    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(questions)")}
    assert "created_by" in cols

    down = alembic("downgrade", "0002")
    assert down.returncode == 0, down.stderr
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(questions)")}
    assert "created_by" not in cols
