"""
The bridge between `POST /generate` and Module A.

Responsibilities, in order:
  1. serve what's already stored (the cache in spec.md Module B),
  2. ask Module A for only the shortfall,
  3. persist the validated batch,
  4. translate Module A's exceptions into the HTTP contract.

The exception mapping is the one prescribed in generation_engine/exceptions.py:

    InvalidRequestError       -> 400 invalid_request
    GroqAPIError              -> 502 groq_api_error
    GenerationValidationError -> 422 validation_failed

Caching semantics: a repeat of an identical request returns the stored
questions rather than burning a Groq call. Send `"refresh": true` to force
fresh generation — that's how the teacher's "generate more" action gets new
questions instead of the same set back.

Figures: with `use_figures` (or explicit `figure_ids`) the questions are written
about figures from the shared figure library (managed by administrators). The model is given each figure's
caption, topic and labelled parts as text and names the figure a question is
about by a short reference; the engine maps that back to the real figure id and
`persist_batch` stores it, so the model never sees or invents an image or an id.
A figure request is served from stored questions only when they use one of the
chosen figures.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.engine import GenerationEngine
from generation_engine.exceptions import (
    GenerationValidationError,
    GroqAPIError,
    InvalidRequestError,
)
from generation_engine.config import settings as engine_settings
from generation_engine.schemas import GenerationRequest

from ..config import settings
from ..errors import BadRequestError, UnprocessableError, UpstreamError
from ..models import Question
from ..schemas.requests import GenerateIn
from . import figures as figure_service
from . import questions as question_service
from .syllabus import get_corpus, get_syllabus_index, resolve_chapter

logger = logging.getLogger("backend.generation")

_engine: GenerationEngine | None = None


def get_engine() -> GenerationEngine:
    """
    Process-wide GenerationEngine.

    Built lazily so importing the app doesn't require a Groq key — tests and
    `--help`-style startups shouldn't need one. Override via `set_engine` in
    tests to stub the Groq call.
    """
    global _engine
    if _engine is None:
        _engine = GenerationEngine(
            syllabus=get_syllabus_index(),
            textbooks=get_corpus(),
            require_textbook=settings.require_textbook,
        )
    return _engine


def set_engine(engine: GenerationEngine | None) -> None:
    """Test/DI hook — pass None to reset."""
    global _engine
    _engine = engine


async def _cached_questions(
    session: AsyncSession,
    payload: GenerateIn,
    chapter_id,
    limit: int,
    figure_ids: list[uuid.UUID] | None = None,
) -> list[Question]:
    """Stored questions that already satisfy this exact request signature.

    For a figure request, `figure_ids` restricts the result to questions about
    one of those figures.
    """
    stmt = (
        select(Question)
        .where(
            Question.is_active.is_(True),
            Question.chapter_id == chapter_id,
            Question.type == payload.type,
            Question.grade == payload.grade,
            Question.marks == payload.marks,
            Question.difficulty == payload.difficulty,
            # A question whose answer key looked wrong is never reused.
            or_(
                Question.verification_status.is_(None),
                Question.verification_status != "flagged",
            ),
        )
        .order_by(Question.created_at.desc(), Question.id)
        .limit(limit)
    )
    if payload.topic:
        stmt = stmt.where(func.lower(Question.topic) == payload.topic.strip().lower())
    if figure_ids is not None:
        stmt = stmt.where(Question.figure_id.in_(figure_ids))
    return list((await session.scalars(stmt)).all())


async def _figures_for(
    session: AsyncSession, payload: GenerateIn, chapter_name: str
) -> list:
    """The figures this request should be about; [] when it does not ask for any."""
    if not payload.wants_figures:
        return []
    limit = settings.max_generation_figures
    if payload.figure_ids:
        return await figure_service.resolve_for_generation(
            session, payload.figure_ids, limit=limit
        )
    figures = await figure_service.library_figures_for_generation(
        session,
        subject=payload.subject.value,
        chapter=chapter_name,
        topic=payload.topic,
        limit=limit,
    )
    if not figures:
        raise BadRequestError(
            f"The figure library has no figures for {payload.subject.value} / {chapter_name}"
            + (f" (topic \"{payload.topic}\")" if payload.topic else "")
            + " with a caption or labelled parts. Ask an administrator to add one, "
            "tagged with this subject and chapter, or turn figures off.",
            error="no_figures",
        )
    return figures


async def generate_questions(
    session: AsyncSession, payload: GenerateIn, *, user_id: uuid.UUID
) -> tuple[list[Question], int, int, dict | None]:
    """
    Returns (questions, cached_count, generated_count, report).

    Raises BadRequestError / UpstreamError / UnprocessableError, which the
    error handlers render as 400 / 502 / 422 in the contract's shape.
    """
    # Resolving the chapter creates the subject/chapter rows if they're new.
    # That's the only write that happens before generation succeeds, and it's
    # reference data rather than question data — "no partial data stored" in
    # test-plan.md is about questions, and none are written on a failure path.
    # Strictly Karnataka State Board: refuse a chapter that isn't in this
    # grade's syllabus BEFORE resolve_chapter would create a row for it.
    corpus = get_corpus()
    if settings.require_textbook and (
        corpus is None or not corpus.has_grade(payload.subject, payload.grade)
    ):
        raise BadRequestError(
            "no Karnataka State Board textbook has been ingested for "
            f"{payload.subject.value} Class {payload.grade}; run "
            "scripts/ingest_textbooks.py on the KTBS PDF first"
        )
    index = get_syllabus_index()
    if index is not None:
        if not index.has_chapter(payload.subject, payload.chapter):
            raise BadRequestError(
                f'unknown chapter "{payload.chapter}" for subject '
                f"{payload.subject.value}"
            )
        if not index.has_chapter(payload.subject, payload.chapter, grade=payload.grade):
            taught_in = index.grades_for_chapter(payload.subject, payload.chapter)
            hint = (
                f" (it is taught in Class {', '.join(str(g) for g in taught_in)})"
                if taught_in
                else ""
            )
            raise BadRequestError(
                f'chapter "{payload.chapter}" is not part of the Karnataka State '
                f"Board Class {payload.grade} {payload.subject.value} syllabus{hint}"
            )
    elif engine_settings.require_syllabus:
        raise BadRequestError(
            "no Karnataka State Board syllabus is loaded; refusing to generate "
            "for an unverified chapter"
        )

    chapter = await resolve_chapter(session, payload.subject, payload.chapter)

    figures = await _figures_for(session, payload, chapter.name)
    figure_ids = [f.id for f in figures] if figures else None

    cached: list[Question] = []
    if settings.enable_generation_cache and not payload.refresh:
        cached = await _cached_questions(
            session, payload, chapter.id, payload.count, figure_ids
        )
        if len(cached) >= payload.count:
            logger.info(
                "Cache hit: %d/%d questions for %s/%s served from storage",
                len(cached),
                payload.count,
                payload.subject.value,
                chapter.name,
            )
            return cached[: payload.count], payload.count, 0, None

    shortfall = payload.count - len(cached)

    # `GenerationRequest` caps `count` at 25 as a pydantic constraint, which
    # would surface as an unhandled ValidationError (500) rather than the 400
    # api-contract.md specifies. Check it here, against the same setting the
    # engine's own validator uses, before constructing the request.
    if payload.count > engine_settings.max_batch_count:
        raise BadRequestError(
            f"count must not exceed {engine_settings.max_batch_count} per request, "
            f"got {payload.count}"
        )

    # Hand the canonical chapter name to Module A so prompts and any syllabus
    # check use the syllabus' own spelling, not the caller's.
    # Walk the chapter's textbook passages from where earlier batches stopped,
    # so repeated generation covers the whole chapter.
    coverage_offset = (
        await session.scalar(
            select(func.count(Question.id)).where(
                Question.is_active.is_(True),
                Question.chapter_id == chapter.id,
                Question.grade == payload.grade,
            )
        )
        or 0
    )

    request = GenerationRequest(
        subject=payload.subject,
        chapter=chapter.name,
        type=payload.type,
        grade=payload.grade,
        marks=payload.marks,
        difficulty=payload.difficulty,
        count=shortfall,
        topic=payload.topic,
        figures=[figure_service.to_context(f) for f in figures] if figures else None,
    )

    engine = get_engine()
    try:
        generated, report = await engine.generate(request)
    except InvalidRequestError as exc:
        raise BadRequestError(exc.detail, error=exc.error) from exc
    except GroqAPIError as exc:
        raise UpstreamError(exc.detail, error=exc.error) from exc
    except GenerationValidationError as exc:
        raise UnprocessableError(exc.detail, error=exc.error) from exc

    logger.info("generation report: %s", report.as_dict())

    stored = await question_service.persist_batch(
        session, generated, chapter=chapter, created_by=user_id
    )

    # persist_batch folds away any question whose text already existed, so the
    # combined list is de-duplicated by identity here rather than by text.
    combined: list[Question] = list(cached)
    seen = {row.id for row in combined}
    for row in stored:
        if row.id not in seen:
            combined.append(row)
            seen.add(row.id)

    return combined[: payload.count], len(cached), len(stored), report.as_dict()
