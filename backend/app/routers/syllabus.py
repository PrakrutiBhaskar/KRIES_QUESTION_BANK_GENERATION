"""
Syllabus / reference data (api-contract.md Section 6).

  GET /subjects
  GET /subjects/{subject}/chapters

`GET /subjects` always returns all five subjects from the shared contract,
whether or not any questions exist for them yet — the frontend's subject
picker shouldn't start empty on a fresh install. Chapters, by contrast, are
only real once they're either seeded from a syllabus file or created by a
generation request, so that list can legitimately come back empty.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import Subject

from ..db import get_session
from ..schemas import ChapterOut, ErrorOut, SubjectOut
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
    subject: Subject, session: AsyncSession = Depends(get_session)
) -> list[ChapterOut]:
    rows = await syllabus_service.list_chapters(session, subject)
    return [
        ChapterOut(
            id=chapter.id,
            name=chapter.name,
            order_index=chapter.order_index,
            question_count=count,
        )
        for chapter, count in rows
    ]
