"""
Database engine / session wiring.

One async engine per process, one session per request. The session dependency
commits on a clean return and rolls back on any exception — which is what
keeps test-plan.md Section 1's "no partial data stored" guarantee true for
the generate path: if validation blows up mid-request, nothing lands.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import CreateColumn

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def build_engine(url: str | None = None, echo: bool | None = None) -> AsyncEngine:
    url = url or settings.database_url
    kwargs: dict = {
        "echo": settings.db_echo if echo is None else echo,
        "future": True,
    }
    if not url.startswith("sqlite"):
        # Modest pool: generation requests are long-lived (they await Groq),
        # so we want a few spare connections rather than a huge pool.
        kwargs.update(pool_size=5, max_overflow=10, pool_pre_ping=True)
    return create_async_engine(url, **kwargs)


# Columns / indexes added after the first release. Base.metadata.create_all()
# only creates *missing tables* and never alters existing ones, so a database
# created by an older version would be missing these. ensure_schema() adds them
# (additive and idempotent). Alembic migration 0003 does the same for
# deployments that use migrations instead of AUTO_CREATE_TABLES (0003 for
# questions.created_by, 0004 for paper_questions.section, 0005 for
# users.preferences, 0006 for the figures table and questions.figure_id /
# answer_figure_id, 0007 for questions.verification_status / verification_note,
# 0008 for the figure metadata used by figure-based generation).
_ADDED_COLUMNS = [
    ("questions", "created_by"),
    ("paper_questions", "section"),
    ("users", "preferences"),
    ("questions", "figure_id"),
    ("questions", "answer_figure_id"),
    ("questions", "verification_status"),
    ("questions", "verification_note"),
    ("figures", "subject"),
    ("figures", "chapter"),
    ("figures", "topic"),
    ("figures", "labels"),
]
_ADDED_INDEXES = [
    ("ix_questions_created_by", "questions", "created_by"),
    ("ix_papers_user_id", "papers", "user_id"),
    ("ix_practice_sessions_user_id", "practice_sessions", "user_id"),
    ("ix_questions_figure_id", "questions", "figure_id"),
    ("ix_questions_answer_figure_id", "questions", "answer_figure_id"),
]


def ensure_schema(sync_conn) -> None:
    """Bring an older database up to date. Run via `conn.run_sync(...)`."""
    inspector = inspect(sync_conn)
    for table, column in _ADDED_COLUMNS:
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            ddl = CreateColumn(Base.metadata.tables[table].columns[column]).compile(
                dialect=sync_conn.dialect
            )
            sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
    for name, table, column in _ADDED_INDEXES:
        sync_conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})"))


engine: AsyncEngine = build_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, commits or rolls back."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
