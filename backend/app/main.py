"""
FastAPI application entrypoint.

Run from the repo root:      uvicorn backend.app.main:app --reload
or from inside backend/:     uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, SessionLocal, ensure_schema
from .deps import get_current_user
from .db import engine as db_engine
from .errors import register_exception_handlers
from .ratelimit import RateLimitMiddleware
from .routers import auth, export, papers, practice, questions, syllabus
from .services.export import active_renderer
from .services.generation import get_engine, set_engine
from .services.syllabus import load_syllabus_index, seed_from_index

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Syllabus first: the GenerationEngine takes the index at construction
    # time, so loading it afterwards would leave the engine without one.
    index = load_syllabus_index()
    set_engine(None)
    get_engine()

    # Fail early, with a readable message, if the database is unreachable —
    # instead of a wall of asyncio/socket traceback.
    try:
        async with db_engine.begin() as conn:
            if settings.should_create_tables:
                from . import models  # noqa: F401  (registers the tables on Base)

                await conn.run_sync(Base.metadata.create_all)
                await conn.run_sync(ensure_schema)
            else:
                await conn.run_sync(lambda c: None)
    except Exception as exc:
        logger.error(
            "Cannot connect to the database at %s: %s\n"
            "  -> Check DATABASE_URL in backend/.env (it overrides the repo-root .env).\n"
            "  -> For local development without PostgreSQL use:\n"
            "       DATABASE_URL=sqlite+aiosqlite:///./question_bank.db",
            _redact(settings.database_url),
            exc,
        )
        raise

    # Pre-create subjects/chapters from the loaded index, if any, so
    # GET /subjects/{subject}/chapters isn't empty on a fresh install —
    # otherwise chapters only appear lazily, after someone generates a
    # question for them first. Idempotent: safe to run on every startup.
    seeded = 0
    if index is not None:
        async with SessionLocal() as session:
            seeded = await seed_from_index(session, index)
            await session.commit()

    if settings.jwt_secret_is_ephemeral:
        logger.warning(
            "JWT_SECRET is not set: using a random per-process key, so everyone "
            "is signed out on every restart. Set JWT_SECRET for any real deployment."
        )

    logger.info(
        "Started %s | db=%s | syllabus=%s | pdf=%s | cache=%s",
        settings.app_name,
        _redact(settings.database_url),
        f"{len(index)} chapters ({seeded} newly seeded)" if index else "none",
        active_renderer(),
        "on" if settings.enable_generation_cache else "off",
    )
    yield
    await db_engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Backend for the Karnataka State Board question bank generator "
        "(grades 7-9). Implements docs/api-contract.md."
    ),
    lifespan=lifespan,
    # Errors are rendered by register_exception_handlers in the contract's
    # {"error", "detail"} shape.
    responses={},
)

# Order matters: middleware added last is outermost. The rate limiter goes in
# first so CORS wraps it — otherwise a 429 would carry no CORS headers and the
# browser would report a network error instead of "too many requests".
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

register_exception_handlers(app)

# Public: sign-up / sign-in. Everything else needs a valid bearer token.
# (The export router guards its own routes: its download link is opened in a
# new browser tab, which can't send an Authorization header, so it uses a
# signed short-lived token instead — see routers/export.py.)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(export.router, prefix=settings.api_prefix)
for router in (questions.router, papers.router, practice.router, syllabus.router):
    app.include_router(
        router, prefix=settings.api_prefix, dependencies=[Depends(get_current_user)]
    )


@app.get("/health", tags=["meta"], summary="Liveness and configuration check")
async def health() -> dict:
    return {
        "status": "ok",
        "api_prefix": settings.api_prefix,
        "pdf_renderer": active_renderer(),
        "generation_cache": settings.enable_generation_cache,
    }


def _redact(url: str) -> str:
    """Hide the password in a connection string before it hits the logs."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"
