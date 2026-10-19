"""
Syllabus / reference data (api-contract.md Section 6).

  GET /subjects
  GET /subjects/{subject}/chapters

`GET /subjects` always returns all six subjects from the shared contract,
whether or not any questions exist for them yet — the frontend's subject
picker shouldn't start empty on a fresh install. Chapters, by contrast, are
only real once they're either seeded from a syllabus file or created by a
generation request, so that list can legitimately come back empty.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import Subject

from ..db import get_session
from ..deps import require_editor
from ..models import User
from ..schemas import (
    ChapterOut,
    ErrorOut,
    SeededChapterOut,
    SeedSyllabusIn,
    SeedSyllabusOut,
    SubjectOut,
)
from ..services import syllabus as syllabus_service

router = APIRouter(tags=["syllabus"])


@router.get("/subjects", response_model=list[SubjectOut], summary="List subjects")
async def list_subjects(
    session: AsyncSession = Depends(get_session),
) -> list[SubjectOut]:
    rows = await syllabus_service.list_subjects(session)
    known = {row.name: (row, count) for row, count in rows}

    out: list[SubjectOut] = []
    for subject in Subject:
        existing = known.get(subject.value)
        if existing:
            row, count = existing
            out.append(
                SubjectOut(
                    id=row.id,
                    name=subject,
                    grade_range=row.grade_range,
                    chapter_count=count,
                )
            )
        else:
            # Not yet persisted — created lazily on first generate. Surfaced
            # with a stable placeholder id so the picker can still render it.
            created = await syllabus_service.get_or_create_subject(session, subject)
            out.append(
                SubjectOut(
                    id=created.id,
                    name=subject,
                    grade_range=created.grade_range,
                    chapter_count=0,
                )
            )
    return out


@router.get(
    "/subjects/{subject}/chapters",
    response_model=list[ChapterOut],
    summary="List chapters for a subject",
    responses={400: {"model": ErrorOut}},
)
async def list_chapters(
    subject: Subject,
    grade: int | None = Query(
        None, ge=7, le=9, description="Only chapters taught in this grade (7-9)."
    ),
    session: AsyncSession = Depends(get_session),
) -> list[ChapterOut]:
    rows = await syllabus_service.list_chapters(session, subject, grade)
    return [
        ChapterOut(
            id=chapter.id,
            name=chapter.name,
            order_index=chapter.order_index,
            question_count=count,
        )
        for chapter, count in rows
    ]


@router.get(
    "/syllabus/seeded",
    response_model=list[SeededChapterOut],
    summary="Chapters added from the Syllabus page",
    description="Teachers and administrators only.",
    responses={403: {"model": ErrorOut}},
)
async def list_seeded_chapters(
    subject: Subject | None = None,
    grade: int | None = Query(None, ge=7, le=9),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
) -> list[SeededChapterOut]:
    rows = await syllabus_service.list_seeded(session, subject, grade)
    return [syllabus_service.seeded_out(r, user) for r in rows]


@router.post(
    "/syllabus/seed",
    response_model=SeedSyllabusOut,
    status_code=status.HTTP_201_CREATED,
    summary="Seed new chapters into a subject's syllabus for one grade",
    description=(
        "Adds chapters (with optional sub-topics) to the live syllabus; they can be "
        "generated from straight away, with no restart. A chapter the grade already has "
        "is skipped. Teachers and administrators only."
    ),
    responses={403: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
async def seed_syllabus(
    payload: SeedSyllabusIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
) -> SeedSyllabusOut:
    added, skipped, warning = await syllabus_service.seed_chapters(
        session, user, payload.subject, payload.grade, payload.chapters
    )
    return SeedSyllabusOut(
        added=[syllabus_service.seeded_out(r, user) for r in added],
        skipped=skipped,
        warning=warning,
    )


@router.delete(
    "/syllabus/seeded/{seeded_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a chapter that was seeded from the app",
    description=(
        "Only the teacher who added it, or an administrator. Questions already generated "
        "for the chapter are kept but the chapter is no longer offered."
    ),
    responses={403: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
async def remove_seeded_chapter(
    seeded_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
) -> Response:
    await syllabus_service.remove_seeded(session, user, seeded_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
