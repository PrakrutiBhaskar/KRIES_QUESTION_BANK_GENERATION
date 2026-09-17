"""
Database engine / session wiring.

One async engine per process, one session per request. The session dependency
commits on a clean return and rolls back on any exception — which is what
keeps test-plan.md Section 1's "no partial data stored" guarantee true for
the generate path: if validation blows up mid-request, nothing lands.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

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
