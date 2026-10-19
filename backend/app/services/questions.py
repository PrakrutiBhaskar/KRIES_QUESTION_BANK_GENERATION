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

from ..errors import BadRequestError, ForbiddenError, NotFoundError
from ..models import Chapter, Question, Subject
from . import figures as figure_service
from .syllabus import get_syllabus_index, resolve_chapter

_WS = re.compile(r"\s+")


def content_hash(
    subject: str,
    chapter_id: uuid.UUID,
    text: str,
    figure_id: uuid.UUID | None = None,
) -> str:
    """
    Stable fingerprint for exact-duplicate detection across batches.

    This is only the cheap exact-match guard. Near-duplicate detection (the
    0.90 similarity threshold) is Module A's job and already runs within a
    batch; doing fuzzy matching against the whole stored bank on every insert
    would mean an O(n) scan per question.
    """
    normalized = _WS.sub(" ", text.strip().lower())
    raw = f"{subject}|{chapter_id}|{normalized}"
    if figure_id is not None:
        # "Label the diagram" with two different diagrams is two questions.
        # Questions without a figure hash exactly as they always did.
        raw += f"|fig:{figure_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def persist_batch(
    session: AsyncSession,
    questions: Sequence[EngineQuestion],
    *,
    chapter: Chapter,
    created_by: uuid.UUID | None = None,
) -> list[Question]:
    """
    Store a validated batch. Questions whose exact text already exists in the
    same chapter are skipped, and the existing row is returned instead, so a
    repeated generate call doesn't grow the bank with the same question twice.
    """
    if not questions:
        return []

    subject_name = questions[0].subject.value
    figure_ids = {q.id: _as_uuid(q.figure_id) for q in questions}
    hashes = {
        q.id: content_hash(subject_name, chapter.id, q.text, figure_ids[q.id])
        for q in questions
    }

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
            # Same question, same key, and this time it was verified: upgrade
            # the stored status (a different key would be a different question).
            if (
                q.verification_status == "verified"
                and prior.verification_status != "verified"
                and prior.answer.strip() == q.answer.strip()
            ):
                prior.verification_status = "verified"
                prior.verification_note = q.verification_note
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
            created_by=created_by,
            verification_status=q.verification_status,
            verification_note=q.verification_note,
            figure_id=figure_ids[q.id],
        )
        session.add(row)
        stored.append(row)

    await session.flush()
    for row in stored:
        # Populate subject/chapter relationships for serialization.
        await session.refresh(
            row, attribute_names=["subject", "chapter", "figure", "answer_figure"]
        )
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


async def create_manual_question(
    session: AsyncSession, payload: Any, *, user_id: uuid.UUID
) -> Question:
    """Store a question the teacher wrote by hand.

    It goes through the same checks as a generated one (shape for its type, marks
    allowed for the type, answer length for the marks), so a hand-written question
    cannot break a paper or the PDF export. It is stored as "unverified" because
    nobody has run the answer check on it, and it is owned by its author.
    """
    index = get_syllabus_index()
    if index is not None and not index.canonical_chapter(payload.subject, payload.chapter):
        raise BadRequestError(
            f'"{payload.chapter}" is not a chapter of {payload.subject.value}.'
        )

    candidate = {
        "subject": payload.subject,
        "chapter": payload.chapter,
        "type": payload.type,
        "grade": payload.grade,
        "text": payload.text,
        "options": [o.strip() for o in payload.options] if payload.options else None,
        "answer": payload.answer,
        "explanation": payload.explanation,
        "marks": payload.marks,
        "difficulty": payload.difficulty,
        "topic": payload.topic,
        "tags": [],
    }
    try:
        validated = EngineQuestion(**candidate)
    except ValidationError as exc:
        raise BadRequestError(_first_error(exc)) from exc

    problems = check_marks_format(validated)
    if problems:
        raise BadRequestError("; ".join(problems))

    chapter = await resolve_chapter(session, payload.subject, payload.chapter)
    new_id = uuid.uuid4()
    # Salted with the id: a hand-written question is always its author's own row and
    # is never merged into (or replaced by) a stored question with the same wording.
    unique_hash = hashlib.sha256(
        f"{content_hash(payload.subject.value, chapter.id, validated.text)}|manual:{new_id}".encode(
            "utf-8"
        )
    ).hexdigest()
    row = Question(
        id=new_id,
        subject_id=chapter.subject_id,
        chapter_id=chapter.id,
        type=validated.type,
        grade=validated.grade,
        text=validated.text,
        options=list(validated.options) if validated.options else None,
        answer=validated.answer,
        explanation=validated.explanation or "",
        marks=validated.marks,
        difficulty=validated.difficulty,
        topic=validated.topic or "",
        tags=[],
        content_hash=unique_hash,
        created_by=user_id,
        verification_status="unverified",
        verification_note="Written by hand; the answer key has not been checked.",
    )
    session.add(row)
    await session.flush()
    await session.refresh(
        row, attribute_names=["subject", "chapter", "figure", "answer_figure"]
    )
    return row


async def copy_question(
    session: AsyncSession, question_id: uuid.UUID, *, user_id: uuid.UUID
) -> Question:
    """Make an editable copy of any question, owned by `user_id`.

    Only the creator may edit a stored question (the pool is shared and other
    people's papers may use it). Someone who wants a different wording or key
    for a question they did not generate edits their own copy instead, and the
    original is left exactly as it was.
    """
    src = await get_question(session, question_id)
    new_id = uuid.uuid4()
    # A distinct fingerprint, so the copy is not treated as a duplicate of the original.
    unique_hash = hashlib.sha256(
        f"{src.content_hash}|copy:{new_id}".encode("utf-8")
    ).hexdigest()
    row = Question(
        id=new_id,
        subject_id=src.subject_id,
        chapter_id=src.chapter_id,
        type=src.type,
        grade=src.grade,
        text=src.text,
        options=list(src.options) if src.options else None,
        answer=src.answer,
        explanation=src.explanation,
        marks=src.marks,
        difficulty=src.difficulty,
        topic=src.topic,
        tags=list(src.tags or []),
        figure_id=src.figure_id,
        answer_figure_id=src.answer_figure_id,
        marks_split=[dict(part) for part in src.marks_split] if src.marks_split else None,
        verification_status=src.verification_status,
        verification_note=src.verification_note,
        content_hash=unique_hash,
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(
        row, attribute_names=["subject", "chapter", "figure", "answer_figure"]
    )
    return row


async def update_question(
    session: AsyncSession,
    question_id: uuid.UUID,
    changes: dict[str, Any],
    *,
    user_id: uuid.UUID,
) -> Question:
    """Apply a partial edit, re-validating the result against Module A.

    The question pool is shared, and papers made by other users may already
    contain this question, so only the person who generated it may change it.
    """
    row = await get_question(session, question_id)
    if row.created_by != user_id:
        raise ForbiddenError("You can only edit questions you generated.")

    # figure_id / answer_figure_id are the one place where an explicit null
    # means something ("detach"), so they are read from `changes` directly.
    figure_keys = [k for k in ("figure_id", "answer_figure_id") if k in changes]
    # marks_split is the same: null means "back to the automatic split".
    split_sent = "marks_split" in changes
    applied = {
        k: v
        for k, v in changes.items()
        if v is not None and k not in ("figure_id", "answer_figure_id", "marks_split")
    }
    if not applied and not figure_keys and not split_sent:
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

    # An edited question or key has not been checked by "Verify answers", so it
    # must not keep a "verified" (or "flagged") result that was earned by the
    # old wording.
    content_changed = (
        validated.text != row.text
        or validated.answer != row.answer
        or (list(validated.options) if validated.options else None) != row.options
    )

    text_changed = validated.text != row.text

    row.text = validated.text
    row.options = list(validated.options) if validated.options else None
    row.answer = validated.answer
    if content_changed:
        row.verification_status = "unverified"
        row.verification_note = "Edited by hand; the answer key has not been checked."
    row.explanation = validated.explanation or ""
    row.marks = validated.marks
    row.difficulty = validated.difficulty
    row.topic = validated.topic or ""
    row.tags = list(validated.tags or [])

    if split_sent:
        row.marks_split = _checked_marks_split(
            changes["marks_split"], validated.marks, validated.type.value
        )
    elif row.marks_split and sum(p["marks"] for p in row.marks_split) != validated.marks:
        # The marks changed, so the old split no longer adds up: fall back to automatic.
        row.marks_split = None

    for key in figure_keys:
        new_id = changes[key]
        if new_id is not None:
            await figure_service.resolve_attachable(session, new_id)
        setattr(row, key, new_id)

    # Only re-fingerprint when the wording or figure changed, so an own copy
    # whose answer alone was edited keeps its distinct hash and is never mistaken
    # for the original by the duplicate guard.
    if text_changed or figure_keys:
        row.content_hash = content_hash(
            row.subject.name, row.chapter_id, row.text, row.figure_id
        )

    await session.flush()
    if figure_keys:
        await session.refresh(row, attribute_names=["figure", "answer_figure"])
    return row


def _checked_marks_split(raw, marks: int, qtype: str) -> list[dict] | None:
    """Validate a teacher's marks split; None clears it (automatic split)."""
    if raw is None:
        return None
    if qtype not in ("Short", "Long") or marks <= 1:
        raise BadRequestError(
            "A marks split only applies to short and long answer questions worth more than 1 mark."
        )
    parts = [{"name": str(p["name"]), "marks": int(p["marks"])} for p in raw]
    if not parts:
        raise BadRequestError("The marks split needs at least one part.")
    names = [p["name"].casefold() for p in parts]
    if len(set(names)) != len(names):
        raise BadRequestError("Each part of the marks split needs a different name.")
    total = sum(p["marks"] for p in parts)
    if total != marks:
        raise BadRequestError(
            f"The marks split adds up to {total}, but this question is worth {marks} marks."
        )
    return parts


async def delete_question(
    session: AsyncSession, question_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    """Soft delete — the row stays so papers/sessions referencing it survive.

    Only the question's creator removes it from the shared pool. Discarding a
    question someone else generated (for example one served from the cache) is
    a successful no-op: the caller's own draft drops it, but other users keep
    it, so nobody can wipe questions out of another teacher's workflow.
    """
    row = await get_question(session, question_id)  # 404 if already discarded
    if row.created_by != user_id:
        return
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
