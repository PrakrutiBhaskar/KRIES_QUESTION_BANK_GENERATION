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

import copy
import json
import logging
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import noload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import Subject as SubjectEnum
from generation_engine.syllabus import SyllabusIndex, _normalize_chapter
from generation_engine.textbook import TextbookCorpus

from ..config import settings
from ..errors import ConflictError, ForbiddenError, NotFoundError
from ..models import Chapter, Question, SeededChapter, Subject, User

logger = logging.getLogger("backend.syllabus")

_syllabus_index: SyllabusIndex | None = None
_corpus: TextbookCorpus | None = None
# subject name -> grade -> normalised chapter names. Optional "grades" block in
# the syllabus JSON; subjects without one aren't grade-filtered.
_grade_chapters: dict[str, dict[int, set[str]]] = {}
# The syllabus as loaded from textbooks + syllabus.json, before any chapters
# seeded from the app are merged in (see reload_seeded).
_base_dict: dict = {}


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
    global _syllabus_index, _grade_chapters, _corpus, _base_dict
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
    _base_dict = copy.deepcopy(merged)

    if not merged:
        logger.info("No syllabus data — chapter names accepted as given.")
        _grade_chapters = {}
        _syllabus_index = None
        return None
    return _install(merged)


def _install(merged: dict) -> SyllabusIndex | None:
    """Build the index from a syllabus dict and make it the live one."""
    global _syllabus_index, _grade_chapters
    if not merged:
        _grade_chapters = {}
        _syllabus_index = None
        return None
    try:
        _syllabus_index = SyllabusIndex.from_dict(merged, strict_grades=True)
        _grade_chapters = _grade_map_from_dict(merged)
        logger.info("Loaded syllabus index (%d chapters)", len(_syllabus_index))
    except ValueError as exc:
        logger.warning("Could not build syllabus index: %s", exc)
        _syllabus_index = None
    return _syllabus_index


def merge_seeded(base: dict, rows: list[SeededChapter]) -> dict:
    """The base syllabus with chapters seeded from the app added to their grade."""
    out = copy.deepcopy(base)
    for row in rows:
        entry = out.setdefault(row.subject, {})
        grades = entry.setdefault("grades", {})
        topics = entry.setdefault("topics", {})
        flat = entry.setdefault("chapters", [])
        in_grade = grades.setdefault(str(row.grade), [])
        key = _normalize_chapter(row.name)
        if key not in {_normalize_chapter(c) for c in in_grade}:
            in_grade.append(row.name)
        if key not in {_normalize_chapter(c) for c in flat}:
            flat.append(row.name)
        if row.topics and not any(_normalize_chapter(c) == key for c in topics):
            topics[row.name] = list(row.topics)
        if not entry["topics"]:
            del entry["topics"]
    return out


async def reload_seeded(session: AsyncSession) -> SyllabusIndex | None:
    """
    Rebuild the live syllabus = textbooks / syllabus.json + chapters seeded from
    the app, hand it to the generation engine, and create the chapter rows.
    Called at startup and after every change on the Syllabus page, so a new
    syllabus applies without a restart.
    """
    rows = list(
        (await session.scalars(select(SeededChapter).order_by(SeededChapter.created_at, SeededChapter.name))).all()
    )
    index = _install(merge_seeded(_base_dict, rows))
    # The engine holds its own reference to the index.
    from . import generation as generation_service

    generation_service.use_syllabus(index)
    if index is not None:
        await seed_from_index(session, index)
    return index


def seeded_out(row: SeededChapter, user: User | None):
    from ..schemas import SeededChapterOut

    return SeededChapterOut(
        id=row.id,
        subject=SubjectEnum(row.subject),
        grade=row.grade,
        name=row.name,
        topics=list(row.topics or []),
        created_by=row.created_by,
        can_remove=bool(user and (user.role == "Admin" or row.created_by == user.id)),
    )


async def list_seeded(
    session: AsyncSession, subject: SubjectEnum | None = None, grade: int | None = None
) -> list[SeededChapter]:
    stmt = select(SeededChapter).order_by(
        SeededChapter.subject, SeededChapter.grade, SeededChapter.created_at, SeededChapter.name
    )
    if subject is not None:
        stmt = stmt.where(SeededChapter.subject == subject.value)
    if grade is not None:
        stmt = stmt.where(SeededChapter.grade == grade)
    return list((await session.scalars(stmt)).all())


async def seed_chapters(
    session: AsyncSession, user: User, subject: SubjectEnum, grade: int, chapters
) -> tuple[list[SeededChapter], list[str], str | None]:
    """
    Add chapters to one subject's syllabus for one grade. Returns (added, skipped
    names, warning). A chapter the grade's syllabus already has is skipped, not
    duplicated; repeats inside the request are skipped too.
    """
    index = get_syllabus_index()
    had_syllabus = bool(_base_dict)
    added: list[SeededChapter] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for ch in chapters:
        key = _normalize_chapter(ch.name)
        if not key or key in seen or (index is not None and index.has_chapter(subject, ch.name, grade)):
            skipped.append(ch.name)
            continue
        seen.add(key)
        row = SeededChapter(
            subject=subject.value,
            grade=grade,
            name=ch.name,
            name_key=key,
            topics=list(ch.topics) or None,
            created_by=user.id,
        )
        session.add(row)
        added.append(row)
    try:
        await session.flush()
    except IntegrityError:
        # A concurrent request seeded the same chapter first.
        await session.rollback()
        raise ConflictError("Some of these chapters were just added by someone else. Reload and try again.")
    if added:
        await reload_seeded(session)
    warning = None
    if added and not had_syllabus:
        warning = (
            "No syllabus was loaded before, so generation now accepts only the chapters "
            "seeded here. Seed every chapter you want to generate from."
        )
    return added, skipped, warning


async def remove_seeded(session: AsyncSession, user: User, seeded_id: uuid.UUID) -> None:
    row = await session.get(SeededChapter, seeded_id)
    if row is None:
        raise NotFoundError("That seeded chapter no longer exists.")
    if user.role != "Admin" and row.created_by != user.id:
        raise ForbiddenError("Only the teacher who added this chapter, or an administrator, can remove it.")
    await session.delete(row)
    await session.flush()
    await reload_seeded(session)


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
            (Question.chapter_id == Chapter.id)
            & (Question.is_active.is_(True))
            # A chapter name can recur in two grades (e.g. Maths "Data Handling");
            # count only the requested grade's questions.
            & ((Question.grade == grade) if grade else True),
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
    if grade and _syllabus_index is not None:
        # Strict: a chapter is listed only under the grade whose syllabus names it.
        rows = [
            (c, n)
            for c, n in rows
            if _syllabus_index.has_chapter(subject, c.name, grade=grade)
        ]
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
