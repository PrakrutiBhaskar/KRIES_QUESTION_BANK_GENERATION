"""
Subject / chapter resolution.

Syllabus ingestion (the PDF-parsing pipeline) is still open — spec.md
Section 8, and task-tracker.md leaves `SyllabusIndex.from_json` as the
drop-in point. Until that lands, the backend can't require chapters to
pre-exist, so `resolve_chapter` creates them on first use.

When a syllabus file *is* supplied (SYLLABUS_JSON_PATH), it's loaded into
Module A's `SyllabusIndex` and handed to the engine, which then rejects
unknown chapters with a 400 — no code change needed here. `seed_from_index`
pre-populates the tables so GET /subjects/{subject}/chapters returns the real
list before anything has been generated.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import Subject as SubjectEnum
from generation_engine.syllabus import SyllabusIndex

from ..config import settings
from ..errors import NotFoundError
from ..models import Chapter, Question, Subject

logger = logging.getLogger("backend.syllabus")

_syllabus_index: SyllabusIndex | None = None


def get_syllabus_index() -> SyllabusIndex | None:
    """The loaded SyllabusIndex, or None when no syllabus data is configured."""
    return _syllabus_index


def load_syllabus_index() -> SyllabusIndex | None:
    """Load SYLLABUS_JSON_PATH once at startup. Missing file is not fatal."""
    global _syllabus_index
    path = settings.syllabus_json_path
    if not path:
        logger.info("No SYLLABUS_JSON_PATH set — chapter names accepted as given.")
        return None
    try:
        _syllabus_index = SyllabusIndex.from_json(path)
        logger.info("Loaded syllabus index (%d chapters) from %s", len(_syllabus_index), path)
    except (OSError, ValueError) as exc:
        logger.warning("Could not load syllabus from %s: %s", path, exc)
        _syllabus_index = None
    return _syllabus_index


async def get_or_create_subject(session: AsyncSession, name: SubjectEnum) -> Subject:
    row = await session.scalar(select(Subject).where(Subject.name == name.value))
    if row:
        return row
    row = Subject(name=name.value, grade_range="7-9")
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        # Lost a race with a concurrent request — take the winner's row.
        await session.rollback()
        row = await session.scalar(select(Subject).where(Subject.name == name.value))
        if row is None:  # pragma: no cover - only if the row vanished again
            raise
    return row


async def resolve_chapter(
    session: AsyncSession, subject: SubjectEnum, chapter_name: str
) -> Chapter:
    """
    Get-or-create a chapter within a subject.

    If a syllabus index is loaded, the name is normalised to the syllabus'
    spelling first, so "ch. 3 photosynthesis" and "Photosynthesis" don't
    become two separate chapters with two separate question banks.
    """
    subject_row = await get_or_create_subject(session, subject)
    name = chapter_name.strip()

    index = get_syllabus_index()
    if index is not None:
        canonical = index.canonical_chapter(subject, name)
        if canonical:
            name = canonical

    row = await session.scalar(
        select(Chapter).where(
            Chapter.subject_id == subject_row.id, func.lower(Chapter.name) == name.lower()
        )
    )
    if row:
        return row

    next_index = await session.scalar(
        select(func.coalesce(func.max(Chapter.order_index), -1) + 1).where(
            Chapter.subject_id == subject_row.id
        )
    )
    row = Chapter(subject_id=subject_row.id, name=name, order_index=next_index or 0)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        row = await session.scalar(
            select(Chapter).where(
                Chapter.subject_id == subject_row.id,
                func.lower(Chapter.name) == name.lower(),
            )
        )
        if row is None:  # pragma: no cover
            raise
    return row


async def find_chapter(
    session: AsyncSession, subject: SubjectEnum, chapter_name: str
) -> Chapter:
    """Look up an existing chapter, or 404. Used by read-only paths."""
    subject_row = await session.scalar(
        select(Subject).where(Subject.name == subject.value)
    )
    if subject_row is None:
        raise NotFoundError(f"No questions stored for subject {subject.value}.")
    row = await session.scalar(
        select(Chapter).where(
            Chapter.subject_id == subject_row.id,
            func.lower(Chapter.name) == chapter_name.strip().lower(),
        )
    )
    if row is None:
        raise NotFoundError(
            f'Unknown chapter "{chapter_name}" for subject {subject.value}.'
        )
    return row


async def list_subjects(session: AsyncSession) -> list[tuple[Subject, int]]:
    """Subjects with their chapter counts (GET /subjects)."""
    stmt = (
        select(Subject, func.count(Chapter.id))
        .outerjoin(Chapter, Chapter.subject_id == Subject.id)
        .group_by(Subject.id)
        .order_by(Subject.name)
    )
    return list((await session.execute(stmt)).all())


async def list_chapters(
    session: AsyncSession, subject: SubjectEnum
) -> list[tuple[Chapter, int]]:
    """Chapters with their (active) question counts."""
    subject_row = await session.scalar(
        select(Subject).where(Subject.name == subject.value)
    )
    if subject_row is None:
        return []
    stmt = (
        select(Chapter, func.count(Question.id))
        .outerjoin(
            Question,
            (Question.chapter_id == Chapter.id) & (Question.is_active.is_(True)),
        )
        .where(Chapter.subject_id == subject_row.id)
        .group_by(Chapter.id)
        .order_by(Chapter.order_index, Chapter.name)
    )
    return list((await session.execute(stmt)).all())


async def seed_from_index(session: AsyncSession, index: SyllabusIndex) -> int:
    """Pre-create subjects/chapters from a SyllabusIndex. Returns rows added."""
    added = 0
    for subject in index.subjects():
        subject_row = await get_or_create_subject(session, subject)
        for order, chapter_name in enumerate(index.chapters(subject)):
            exists = await session.scalar(
                select(Chapter.id).where(
                    Chapter.subject_id == subject_row.id,
                    func.lower(Chapter.name) == chapter_name.lower(),
                )
            )
            if exists:
                continue
            session.add(
                Chapter(
                    subject_id=subject_row.id, name=chapter_name, order_index=order
                )
            )
            added += 1
    await session.flush()
    return added
