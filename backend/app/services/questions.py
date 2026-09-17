"""
Question storage and retrieval.

Persistence rule (test-plan.md Section 1): questions are written only after
Module A has returned a fully validated batch. Nothing here is called on the
error paths, and the request-scoped transaction in db.py rolls back if
anything fails mid-write — so a 400/502/422 never leaves partial data.

Re-validation on edit: PATCH runs the edited row back through Module A's
`Question` model and `check_marks_format`, so a teacher can't hand-edit a
3-mark answer down to one line and have it persist. The API owns storage;
Module A stays the authority on what a valid question looks like.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any, Sequence

from pydantic import ValidationError
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import Difficulty, QuestionType, Subject as SubjectEnum
from generation_engine.schemas import Question as EngineQuestion
from generation_engine.validation import check_marks_format

from ..errors import BadRequestError, NotFoundError
from ..models import Chapter, Question, Subject
from .syllabus import resolve_chapter

_WS = re.compile(r"\s+")


def content_hash(subject: str, chapter_id: uuid.UUID, text: str) -> str:
    """
    Stable fingerprint for exact-duplicate detection across batches.

    This is only the cheap exact-match guard. Near-duplicate detection (the
    0.90 similarity threshold) is Module A's job and already runs within a
    batch; doing fuzzy matching against the whole stored bank on every insert
    would mean an O(n) scan per question.
    """
    normalized = _WS.sub(" ", text.strip().lower())
    raw = f"{subject}|{chapter_id}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def persist_batch(
    session: AsyncSession,
    questions: Sequence[EngineQuestion],
    *,
    chapter: Chapter,
) -> list[Question]:
    """
    Store a validated batch. Questions whose exact text already exists in the
    same chapter are skipped, and the existing row is returned instead, so a
    repeated generate call doesn't grow the bank with the same question twice.
    """
    if not questions:
        return []

    subject_name = questions[0].subject.value
    hashes = {q.id: content_hash(subject_name, chapter.id, q.text) for q in questions}

    existing_rows = (
        await session.scalars(
            select(Question).where(Question.content_hash.in_(list(hashes.values())))
        )
    ).all()
    existing_by_hash = {row.content_hash: row for row in existing_rows}

    stored: list[Question] = []
    seen: set[str] = set()
    for q in questions:
        h = hashes[q.id]
        if h in seen:  # duplicate inside this same batch
            continue
        seen.add(h)

        prior = existing_by_hash.get(h)
        if prior is not None:
            if not prior.is_active:
                prior.is_active = True  # resurrect a previously discarded twin
            stored.append(prior)
            continue

        row = Question(
            id=uuid.UUID(q.id) if isinstance(q.id, str) else q.id,
            subject_id=chapter.subject_id,
            chapter_id=chapter.id,
            type=q.type,
            grade=q.grade,
            text=q.text,
            options=list(q.options) if q.options else None,
            answer=q.answer,
            explanation=q.explanation or "",
            marks=q.marks,
            difficulty=q.difficulty,
            topic=q.topic or "",
            tags=list(q.tags or []),
            content_hash=h,
        )
        session.add(row)
        stored.append(row)

    await session.flush()
    for row in stored:
        # Populate subject/chapter relationships for serialization.
        await session.refresh(row, attribute_names=["subject", "chapter"])
    return stored


def _base_query() -> Select:
    return select(Question).where(Question.is_active.is_(True))


def build_filter_query(
    *,
    subject: SubjectEnum | None = None,
    chapter: str | None = None,
    type: QuestionType | None = None,
    grade: int | None = None,
    marks: int | None = None,
    difficulty: Difficulty | None = None,
    topic: str | None = None,
    search: str | None = None,
) -> Select:
    """
    Build the GET /questions filter query.

    Filters compose — every supplied param is ANDed, which is what
    test-plan.md Section 2 means by "filters work individually and combined".
    """
    stmt = _base_query()
    if subject is not None:
        stmt = stmt.join(Subject, Question.subject_id == Subject.id).where(
            Subject.name == subject.value
        )
    if chapter is not None:
        stmt = stmt.join(Chapter, Question.chapter_id == Chapter.id).where(
            func.lower(Chapter.name) == chapter.strip().lower()
        )
    if type is not None:
        stmt = stmt.where(Question.type == type)
    if grade is not None:
        stmt = stmt.where(Question.grade == grade)
    if marks is not None:
        stmt = stmt.where(Question.marks == marks)
    if difficulty is not None:
        stmt = stmt.where(Question.difficulty == difficulty)
    if topic is not None:
        stmt = stmt.where(func.lower(Question.topic) == topic.strip().lower())
    if search:
        needle = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Question.text).like(needle),
                func.lower(Question.answer).like(needle),
                func.lower(Question.topic).like(needle),
            )
        )
    return stmt


async def paginate(
    session: AsyncSession, stmt: Select, *, page: int, page_size: int
) -> tuple[list[Question], int]:
    total = await session.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    rows = (
        await session.scalars(
            stmt.order_by(Question.created_at.desc(), Question.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return list(rows), int(total or 0)


async def get_question(session: AsyncSession, question_id: uuid.UUID) -> Question:
    row = await session.scalar(
        _base_query().where(Question.id == question_id)
    )
    if row is None:
        raise NotFoundError(f"Question {question_id} not found.")
    return row


async def get_questions_by_ids(
    session: AsyncSession, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Question]:
    if not ids:
        return {}
    rows = (await session.scalars(_base_query().where(Question.id.in_(list(ids))))).all()
    return {row.id: row for row in rows}


async def update_question(
    session: AsyncSession, question_id: uuid.UUID, changes: dict[str, Any]
) -> Question:
    """Apply a partial edit, re-validating the result against Module A."""
    row = await get_question(session, question_id)

    applied = {k: v for k, v in changes.items() if v is not None}
    if not applied:
        return row

    candidate = {
        "id": str(row.id),
        "subject": row.subject.name,
        "chapter": row.chapter.name,
        "type": row.type,
        "grade": row.grade,
        "text": applied.get("text", row.text),
        "options": applied.get("options", row.options),
        "answer": applied.get("answer", row.answer),
        "explanation": applied.get("explanation", row.explanation),
        "marks": applied.get("marks", row.marks),
        "difficulty": applied.get("difficulty", row.difficulty),
        "topic": applied.get("topic", row.topic),
        "tags": applied.get("tags", list(row.tags or [])),
    }

    try:
        validated = EngineQuestion(**candidate)
    except ValidationError as exc:
        raise BadRequestError(_first_error(exc)) from exc

    problems = check_marks_format(validated)
    if problems:
        raise BadRequestError("; ".join(problems))

    row.text = validated.text
    row.options = list(validated.options) if validated.options else None
    row.answer = validated.answer
    row.explanation = validated.explanation or ""
    row.marks = validated.marks
    row.difficulty = validated.difficulty
    row.topic = validated.topic or ""
    row.tags = list(validated.tags or [])
    row.content_hash = content_hash(row.subject.name, row.chapter_id, row.text)

    await session.flush()
    return row


async def delete_question(session: AsyncSession, question_id: uuid.UUID) -> None:
    """Soft delete — the row stays so papers/sessions referencing it survive."""
    row = await get_question(session, question_id)  # 404 if already discarded
    row.is_active = False
    await session.flush()


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:  # pragma: no cover
        return "invalid question"
    first = errors[0]
    loc = ".".join(str(p) for p in first.get("loc", ()))
    msg = first.get("msg", "invalid value")
    return f"{loc}: {msg}" if loc else msg
