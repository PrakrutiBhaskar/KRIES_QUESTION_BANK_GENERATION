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

import json
import logging
import re

from sqlalchemy import func, select
from sqlalchemy.orm import noload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import Subject as SubjectEnum
from generation_engine.syllabus import SyllabusIndex
from generation_engine.textbook import TextbookCorpus

from ..config import settings
from ..errors import NotFoundError
from ..models import Chapter, Question, Subject

logger = logging.getLogger("backend.syllabus")

_syllabus_index: SyllabusIndex | None = None
_corpus: TextbookCorpus | None = None
# subject name -> grade -> normalised chapter names. Optional "grades" block in
# the syllabus JSON; subjects without one (English) aren't grade-filtered.
_grade_chapters: dict[str, dict[int, set[str]]] = {}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _grade_map_from_dict(raw: dict) -> dict[str, dict[int, set[str]]]:
    out: dict[str, dict[int, set[str]]] = {}
    for subject, entry in raw.items():
        grades = entry.get("grades") if isinstance(entry, dict) else None
        if not isinstance(grades, dict):
            continue
        out[subject] = {
            int(g): {_norm(str(c)) for c in chapters} for g, chapters in grades.items()
        }
    return out


def _load_grade_map(path) -> dict[str, dict[int, set[str]]]:
    """Grade map straight from a syllabus JSON file (kept for tests/tools)."""
    with open(path, "r", encoding="utf-8") as fh:
        return _grade_map_from_dict(json.load(fh))


def get_corpus() -> TextbookCorpus | None:
    """The ingested KTBS textbooks, or None when none are available."""
    return _corpus


def get_syllabus_index() -> SyllabusIndex | None:
    """The loaded SyllabusIndex, or None when no syllabus data is configured."""
    return _syllabus_index


def load_syllabus_index() -> SyllabusIndex | None:
    """
    Build the syllabus at startup.

    1. Load the ingested KTBS textbooks (TEXTBOOKS_DIR). Their chapters, grades
       and section titles define the syllabus for every (subject, grade) they
       cover.
    2. REQUIRE_TEXTBOOK=true: that is the whole syllabus — syllabus.json is not
       read, so nothing is hardcoded.
       Otherwise the bundled syllabus.json fills in (subject, grade) pairs with
       no textbook yet, and textbooks override it where present.
    """
    global _syllabus_index, _grade_chapters, _corpus
    _corpus = TextbookCorpus.from_dir(settings.textbooks_dir)
    if _corpus.is_empty():
        logger.warning(
            "No textbook corpus in %s — generation is not textbook-grounded. "
            "Run scripts/ingest_textbooks.py on the KTBS PDFs.",
            settings.textbooks_dir,
        )
        if settings.require_textbook:
            logger.error("REQUIRE_TEXTBOOK is on but no textbooks are ingested: every generate request will be refused.")
    else:
        logger.info(
            "Loaded textbook corpus: %s",
            ", ".join(f"{s.value} {g}" for s in _corpus.subjects() for g in _corpus.grades(s)),
        )

    base: dict = {}
    path = settings.syllabus_json_path
    if path and not settings.require_textbook:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                base = {k: v for k, v in json.load(fh).items() if not str(k).startswith("_")}
        except (OSError, ValueError) as exc:
            logger.warning("Could not read syllabus from %s: %s", path, exc)
    merged = _corpus.to_syllabus_dict(base)

    if not merged:
        logger.info("No syllabus data — chapter names accepted as given.")
        _grade_chapters = {}
        _syllabus_index = None
        return None
    try:
        _syllabus_index = SyllabusIndex.from_dict(merged)
        _grade_chapters = _grade_map_from_dict(merged)
        logger.info("Loaded syllabus index (%d chapters)", len(_syllabus_index))
    except ValueError as exc:
        logger.warning("Could not build syllabus index: %s", exc)
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
        # Don't pull every chapter row via the selectin relationship just to count them.
        .options(noload(Subject.chapters))
        .outerjoin(Chapter, Chapter.subject_id == Subject.id)
        .group_by(Subject.id)
        .order_by(Subject.name)
    )
    return list((await session.execute(stmt)).all())


async def list_chapters(
    session: AsyncSession, subject: SubjectEnum, grade: int | None = None
) -> list[tuple[Chapter, int]]:
    """
    Chapters with their (active) question counts.

    With ``grade`` set, only that grade's chapters are returned — provided the
    syllabus file has a "grades" block for the subject. Otherwise (no block, or
    no syllabus loaded) every chapter is returned, as before.
    """
    subject_row = await session.scalar(
        select(Subject).where(Subject.name == subject.value)
    )
    if subject_row is None:
        return []
    stmt = (
        select(Chapter, func.count(Question.id))
        # Chapter.subject is lazy="joined" on the model. Left in place it adds
        # the subjects columns to a query that only GROUPs BY chapters.id, which
        # PostgreSQL rejects (500) although SQLite tolerates it. The caller only
        # needs chapter columns + the count, so switch the eager load off here.
        .options(noload(Chapter.subject))
        .outerjoin(
            Question,
            (Question.chapter_id == Chapter.id) & (Question.is_active.is_(True)),
        )
        .where(Chapter.subject_id == subject_row.id)
        .group_by(Chapter.id)
        .order_by(Chapter.order_index, Chapter.name)
    )
    rows = list((await session.execute(stmt)).all())
    # With a syllabus loaded, chapters left in the DB from an older chapter
    # list (or created before the syllabus was enforced) are not offered.
    if _syllabus_index is not None:
        rows = [
            (c, n) for c, n in rows if _syllabus_index.has_chapter(subject, c.name)
        ]
    allowed = _grade_chapters.get(subject.value, {}).get(grade) if grade else None
    if allowed is not None:
        rows = [(c, n) for c, n in rows if _norm(c.name) in allowed]
    return rows


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
