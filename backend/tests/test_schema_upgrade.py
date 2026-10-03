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


async def test_ensure_schema_adds_figure_columns_to_an_old_database(tmp_path):
    db = tmp_path / "prefig.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db}"}
    # A real pre-figures database: migrate to 0005 (SQLite cannot DROP a column
    # that sits in a foreign key, so we build the old schema rather than strip it).
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0005"],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True,
    )
    assert up.returncode == 0, up.stderr

    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    assert "figure_id" not in await _columns(engine, "questions")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # creates the figures table
        await conn.run_sync(ensure_schema)

    cols = await _columns(engine, "questions")
    assert {"figure_id", "answer_figure_id"} <= cols
    assert "ix_questions_figure_id" in await _indexes(engine, "questions")
    assert "ix_questions_answer_figure_id" in await _indexes(engine, "questions")

    async with engine.begin() as conn:  # and it is safe on every startup
        await conn.run_sync(ensure_schema)
    await engine.dispose()


async def test_ensure_schema_adds_figure_metadata_columns_to_an_existing_figures_table(tmp_path):
    db = tmp_path / "figmeta.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db}"}
    # A database as released with figures but before figure metadata (0007).
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0007"],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True,
    )
    assert up.returncode == 0, up.stderr

    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    assert not {"subject", "chapter", "topic", "labels"} & await _columns(engine, "figures")

    async with engine.begin() as conn:
        await conn.run_sync(ensure_schema)
    assert {"subject", "chapter", "topic", "labels"} <= await _columns(engine, "figures")

    async with engine.begin() as conn:  # idempotent
        await conn.run_sync(ensure_schema)
    await engine.dispose()


async def test_ensure_schema_adds_the_new_column_and_indexes_to_an_old_database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Turn it back into what a pre-ownership database looked like.
        for index in ("ix_questions_created_by", "ix_papers_user_id", "ix_practice_sessions_user_id"):
            await conn.execute(text(f"DROP INDEX {index}"))
        for column in ("created_by", "verification_status", "verification_note"):
            await conn.execute(text(f"ALTER TABLE questions DROP COLUMN {column}"))
    assert "created_by" not in await _columns(engine, "questions")

    async with engine.begin() as conn:
        await conn.run_sync(ensure_schema)

    columns = await _columns(engine, "questions")
    assert {"created_by", "verification_status", "verification_note"} <= columns
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
    assert {"created_by", "verification_status", "verification_note"} <= cols
    assert {"figure_id", "answer_figure_id"} <= cols
    tables = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "figures" in tables
    fig_cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(figures)")}
    assert {"subject", "chapter", "topic", "labels"} <= fig_cols

    # 0008 (figure metadata) comes off cleanly and goes back on.
    metadata_off = alembic("downgrade", "0007")
    assert metadata_off.returncode == 0, metadata_off.stderr
    fig_cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(figures)")}
    assert not {"subject", "chapter", "topic", "labels"} & fig_cols
    assert {"caption", "filename"} <= fig_cols
    assert alembic("upgrade", "head").returncode == 0

    # Step back over the three newest migrations (figures 0006, answer
    # verification 0007, figure metadata 0008), then on down to 0002.
    one = alembic("downgrade", "0005")
    assert one.returncode == 0, one.stderr
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(questions)")}
    assert not {"figure_id", "answer_figure_id", "verification_status", "verification_note"} & cols
    assert "created_by" in cols
    again = alembic("upgrade", "head")
    assert again.returncode == 0, again.stderr

    down = alembic("downgrade", "0002")
    assert down.returncode == 0, down.stderr
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(questions)")}
    assert not {"created_by", "verification_status", "verification_note"} & cols
