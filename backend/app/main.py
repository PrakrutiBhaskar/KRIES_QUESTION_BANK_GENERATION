"""
FastAPI application entrypoint.

Run from the repo root:      uvicorn backend.app.main:app --reload
or from inside backend/:     uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .errors import register_exception_handlers
from .routers import export, papers, practice, questions, syllabus
from .services.export import active_renderer
from .services.generation import get_engine, set_engine
from .services.syllabus import load_syllabus_index

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

    logger.info(
        "Started %s | db=%s | syllabus=%s | pdf=%s | cache=%s",
        settings.app_name,
        _redact(settings.database_url),
        f"{len(index)} chapters" if index else "none",
        active_renderer(),
        "on" if settings.enable_generation_cache else "off",
    )
    yield
    from .db import engine

    await engine.dispose()


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

for router in (questions.router, papers.router, export.router, practice.router, syllabus.router):
    app.include_router(router, prefix=settings.api_prefix)


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
