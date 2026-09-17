"""
Generation and question-bank endpoints.

  POST   /generate            api-contract.md Section 1
  GET    /questions           api-contract.md Section 2
  GET    /questions/{id}
  PATCH  /questions/{id}
  DELETE /questions/{id}
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import Difficulty, QuestionType, Subject

from ..db import get_session
from ..schemas import (
    ErrorOut,
    GenerateIn,
    GenerateOut,
    Page,
    QuestionOut,
    QuestionPatch,
)
from ..services import generation as generation_service
from ..services import questions as question_service

router = APIRouter(tags=["questions"])


@router.post(
    "/generate",
    response_model=GenerateOut,
    summary="Generate a batch of questions",
    responses={
        400: {"model": ErrorOut, "description": "Invalid subject/chapter/type/marks combination"},
        422: {"model": ErrorOut, "description": "Generated output failed validation"},
        502: {"model": ErrorOut, "description": "Groq API call failed"},
    },
)
async def generate(
    payload: GenerateIn, session: AsyncSession = Depends(get_session)
) -> GenerateOut:
    questions, cached, generated, report = await generation_service.generate_questions(
        session, payload
    )
    return GenerateOut(
        questions=[QuestionOut.from_model(q) for q in questions],
        cached=cached,
        generated=generated,
        report=report,
    )


@router.get(
    "/questions",
    response_model=Page[QuestionOut],
    summary="Filter and search stored questions",
)
async def list_questions(
    subject: Subject | None = None,
    chapter: str | None = None,
    type: QuestionType | None = None,
    grade: int | None = Query(default=None, ge=7, le=9),
    marks: int | None = Query(default=None),
    difficulty: Difficulty | None = None,
    topic: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> Page[QuestionOut]:
    stmt = question_service.build_filter_query(
        subject=subject,
        chapter=chapter,
        type=type,
        grade=grade,
        marks=marks,
        difficulty=difficulty,
        topic=topic,
        search=search,
    )
    rows, total = await question_service.paginate(
        session, stmt, page=page, page_size=page_size
    )
    return Page[QuestionOut](
        results=[QuestionOut.from_model(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/questions/{question_id}",
    response_model=QuestionOut,
    responses={404: {"model": ErrorOut}},
)
async def get_question(
    question_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> QuestionOut:
    row = await question_service.get_question(session, question_id)
    return QuestionOut.from_model(row)


@router.patch(
    "/questions/{question_id}",
    response_model=QuestionOut,
    summary="Edit a question (teacher curation)",
    responses={400: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
async def patch_question(
    question_id: uuid.UUID,
    payload: QuestionPatch,
    session: AsyncSession = Depends(get_session),
) -> QuestionOut:
    row = await question_service.update_question(
        session, question_id, payload.model_dump(exclude_unset=True)
    )
    return QuestionOut.from_model(row)


@router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Discard a question",
    responses={404: {"model": ErrorOut}},
)
async def delete_question(
    question_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> Response:
    await question_service.delete_question(session, question_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
