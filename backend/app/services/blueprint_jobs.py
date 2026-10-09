"""
Background paper builds, so the browser can show real progress.

`POST /papers/blueprint` does everything inside one request and only answers when
the paper is finished, which for a big paper can be a minute or two of silence.
This module runs the same build (`blueprint.create_blueprint_paper`, unchanged
apart from a progress callback) as a background task and keeps a small record of
how far it has got, which `GET /papers/blueprint/jobs/{id}` reports.

Guarantees are the same as the one-shot endpoint: the build runs in a single
transaction, so a failure anywhere stores no paper and no new questions.

Limits, on purpose:
  * Jobs live in this process's memory. A server restart (or a second worker
    process answering the poll) loses them: the poll gets a 404 and the user is
    told to look in Question Banks, because a finished paper is already saved.
    Run a single worker, or move this registry to Redis/the database, if that
    matters.
  * One running build per user at a time (409 otherwise), so a double click
    doesn't pay for two papers.
  * Finished jobs are forgotten after JOB_TTL_SECONDS.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal
from ..errors import APIError, ConflictError, NotFoundError
from ..schemas import BlueprintIn, BlueprintJobOut, PaperOut
from . import blueprint as blueprint_service
from .generation_budget import budget_for

logger = logging.getLogger("backend.blueprint_jobs")

JOB_TTL_SECONDS = 60 * 60


@dataclass
class Job:
    id: uuid.UUID
    user_id: uuid.UUID
    status: str = "running"
    done: int = 0
    total: int = 0
    paper: PaperOut | None = None
    error: str | None = None
    detail: str | None = None
    error_status: int | None = None
    finished_at: float | None = None

    def to_out(self) -> BlueprintJobOut:
        return BlueprintJobOut(
            id=self.id,
            status=self.status,  # type: ignore[arg-type]
            done=self.done,
            total=self.total,
            paper=self.paper,
            error=self.error,
            detail=self.detail,
            error_status=self.error_status,
        )


_jobs: dict[uuid.UUID, Job] = {}
_tasks: set[asyncio.Task] = set()  # keeps running tasks from being garbage collected

# Where the job's own database session comes from. Tests swap it for the in-memory one.
_session_factory: Callable[[], AsyncSession] = SessionLocal


def set_session_factory(factory: Callable[[], AsyncSession] | None) -> None:
    global _session_factory
    _session_factory = factory or SessionLocal


def _forget_old_jobs() -> None:
    cutoff = time.monotonic() - JOB_TTL_SECONDS
    for job_id in [j.id for j in _jobs.values() if j.finished_at and j.finished_at < cutoff]:
        del _jobs[job_id]


async def _run(job: Job, blueprint: BlueprintIn, role: str | None) -> None:
    def progress(done: int, total: int) -> None:
        job.done, job.total = done, total

    try:
        async with _session_factory() as session:
            try:
                budget = await budget_for(session, user_id=job.user_id, role=role)
                paper = await blueprint_service.create_blueprint_paper(
                    session, blueprint, job.user_id, on_progress=progress, budget=budget
                )
                job.paper = PaperOut.from_model(paper)
                await session.commit()
            except BaseException:
                await session.rollback()
                raise
        job.done = job.total
        job.status = "done"
    except APIError as exc:
        job.status, job.error, job.detail, job.error_status = (
            "error",
            exc.error,
            exc.detail,
            exc.status_code,
        )
    except Exception:
        logger.exception("Background paper build %s failed", job.id)
        job.status, job.error, job.error_status = "error", "internal_error", 500
        job.detail = "Something went wrong while building the paper. Nothing was saved."
    finally:
        job.finished_at = time.monotonic()


def start(blueprint: BlueprintIn, user_id: uuid.UUID, role: str | None = None) -> Job:
    _forget_old_jobs()
    if any(j.user_id == user_id and j.status == "running" for j in _jobs.values()):
        raise ConflictError(
            "A paper is already being built for your account. Wait for it to finish.",
            error="paper_in_progress",
        )
    job = Job(id=uuid.uuid4(), user_id=user_id)
    _jobs[job.id] = job
    task = asyncio.create_task(_run(job, blueprint, role))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job


def get(job_id: uuid.UUID, user_id: uuid.UUID) -> Job:
    job = _jobs.get(job_id)
    if job is None or job.user_id != user_id:
        raise NotFoundError(
            "That paper build was not found. If the server restarted, check Question Banks: "
            "a finished paper is already saved there."
        )
    return job


def reset() -> None:
    """Forget every job (tests)."""
    _jobs.clear()
