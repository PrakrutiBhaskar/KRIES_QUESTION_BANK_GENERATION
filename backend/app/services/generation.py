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

Answer-key verification is not part of generation. `verify_questions` below is
a separate, on-demand step (POST /questions/verify, the "Verify answers" button):
generation stays fast and returns questions as "unverified" until someone asks.
"""
from __future__ import annotations

import logging
import random
import uuid
from typing import Sequence

from pydantic import ValidationError
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
from generation_engine.schemas import Question as EngineQuestion

from ..config import settings
from ..errors import BadRequestError, NotFoundError, UnprocessableError, UpstreamError
from ..models import Question
from ..schemas.requests import GenerateIn
from . import figures as figure_service
from . import questions as question_service
from .generation_budget import GenerationBudget
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
    else:
        # A plain (theory) request never reuses a stored diagram-based question.
        stmt = stmt.where(Question.figure_id.is_(None))
    return list((await session.scalars(stmt)).all())


async def count_stored(
    session: AsyncSession,
    *,
    chapter_id,
    q_type,
    grade: int,
    marks: int,
    difficulty: str,
    with_figures: bool,
) -> int:
    """How many stored questions could serve a request with this signature.

    Same filters as `_cached_questions`; used to estimate, before any model call,
    how many new questions a paper would need (see blueprint.py). For a figure
    request any stored diagram question in the chapter counts.
    """
    stmt = select(func.count(Question.id)).where(
        Question.is_active.is_(True),
        Question.chapter_id == chapter_id,
        Question.type == q_type,
        Question.grade == grade,
        Question.marks == marks,
        Question.difficulty == difficulty,
        or_(
            Question.verification_status.is_(None),
            Question.verification_status != "flagged",
        ),
        Question.figure_id.is_not(None) if with_figures else Question.figure_id.is_(None),
    )
    return int((await session.scalar(stmt)) or 0)


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


def _random_figure_count(count: int) -> int:
    """How many of `count` questions to write about figures, chosen at random.

    Between one and half of them when there are two or more (so a bank is never
    all theory and never mostly diagrams); a lone question is a diagram question
    about one time in three.
    """
    if count < 2:
        return 1 if random.random() < 1 / 3 else 0
    return random.randint(1, max(1, count // 2))


async def generate_questions(
    session: AsyncSession,
    payload: GenerateIn,
    *,
    user_id: uuid.UUID,
    budget: GenerationBudget | None = None,
) -> tuple[list[Question], int, int, dict | None]:
    """Like `_generate_once`, but honours `payload.mix_figures`.

    `budget` (set for student accounts, see generation_budget.py) caps how many
    new questions the model may be asked for; stored questions are always used
    first and never count against it.

    With `mix_figures`, a random number of the questions are written about
    figures from the library and the rest are theory; the result is shuffled so
    the diagram questions land at random positions. When the chapter has no
    usable figure, every question is theory.
    """
    if not payload.mix_figures or payload.wants_figures:
        return await _generate_once(session, payload, user_id=user_id, budget=budget)

    theory = payload.model_copy(update={"mix_figures": False})
    n_figures = _random_figure_count(payload.count)
    if n_figures == 0:
        return await _generate_once(session, theory, user_id=user_id, budget=budget)

    figure_payload = theory.model_copy(update={"use_figures": True, "count": n_figures})
    try:
        fig_qs, fig_cached, fig_new, fig_report = await _generate_once(
            session, figure_payload, user_id=user_id, budget=budget
        )
    except BadRequestError as exc:
        if exc.error != "no_figures":
            raise
        return await _generate_once(session, theory, user_id=user_id, budget=budget)

    remaining = payload.count - n_figures
    if remaining <= 0:
        return fig_qs, fig_cached, fig_new, fig_report

    plain = theory.model_copy(update={"count": remaining})
    th_qs, th_cached, th_new, th_report = await _generate_once(
        session, plain, user_id=user_id, budget=budget
    )

    combined = list(fig_qs)
    seen = {q.id for q in combined}
    for q in th_qs:
        if q.id not in seen:
            combined.append(q)
            seen.add(q.id)
    random.shuffle(combined)
    return combined, fig_cached + th_cached, fig_new + th_new, th_report or fig_report


async def _generate_once(
    session: AsyncSession,
    payload: GenerateIn,
    *,
    user_id: uuid.UUID,
    budget: GenerationBudget | None = None,
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

    # Only the shortfall ever reaches the model. A student's allowance is
    # charged now, before the call, so a request they cannot afford is refused
    # without spending anything.
    if budget is not None:
        budget.reserve(shortfall)

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


# ---------------------------------------------------------------------------
# On-demand answer-key verification
# ---------------------------------------------------------------------------

_UNCHECKABLE_NOTE = "Could not be checked: the stored question is not in a checkable format."


def _to_engine_question(row: Question) -> EngineQuestion:
    """The stored row as Module A's Question, with the figure's text description."""
    figure_context = (
        figure_service.to_context(row.figure).describe() if row.figure is not None else None
    )
    return EngineQuestion(
        id=str(row.id),
        subject=row.subject.name,
        chapter=row.chapter.name,
        type=row.type,
        grade=row.grade,
        text=row.text,
        options=list(row.options) if row.options else None,
        answer=row.answer,
        explanation=row.explanation or "",
        marks=row.marks,
        difficulty=row.difficulty,
        topic=row.topic or "",
        tags=list(row.tags or []),
        figure_id=str(row.figure_id) if row.figure_id else None,
        figure_context=figure_context,
    )


async def verify_questions(
    session: AsyncSession, question_ids: Sequence[uuid.UUID]
) -> list[Question]:
    """
    Check the answer keys of stored questions and save the result on each row.

    Rule checks run first, then (if enabled) one independent AI pass per chunk
    for whatever the rules couldn't decide. This never fails because the AI
    pass did: a Groq error just leaves those questions "unverified".

    Any signed-in user may verify any stored question: the result is metadata
    about the answer key, not an edit to the question, and the pool is shared.
    Returns the rows in the order requested.
    """
    ids = list(dict.fromkeys(question_ids))  # de-duplicate, keep order
    rows_by_id = await question_service.get_questions_by_ids(session, ids)
    missing = [str(i) for i in ids if i not in rows_by_id]
    if missing:
        raise NotFoundError(f"Question(s) not found: {', '.join(missing)}.")
    rows = [rows_by_id[i] for i in ids]

    checkable: list[tuple[Question, EngineQuestion]] = []
    for row in rows:
        try:
            checkable.append((row, _to_engine_question(row)))
        except ValidationError:
            logger.warning("Question %s cannot be verified: invalid stored shape", row.id)
            row.verification_status = "unverified"
            row.verification_note = _UNCHECKABLE_NOTE

    if checkable:
        checked = await get_engine().verify_answers([eq for _, eq in checkable])
        for (row, _), result in zip(checkable, checked):
            row.verification_status = result.verification_status
            row.verification_note = result.verification_note

    await session.flush()
    return rows
