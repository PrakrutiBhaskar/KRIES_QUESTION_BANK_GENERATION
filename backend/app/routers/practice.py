"""
Practice mode endpoints (api-contract.md Section 5).

  POST /practice/sessions
  GET  /practice/sessions/{id}
  GET  /practice/sessions/{id}/reveal/{question_id}
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..schemas import ErrorOut, PracticeSessionIn, PracticeSessionOut, RevealOut
from ..services import practice as practice_service

router = APIRouter(prefix="/practice", tags=["practice"])


@router.post(
    "/sessions",
    response_model=PracticeSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a practice session (answers withheld)",
    responses={
        400: {"model": ErrorOut},
        422: {"model": ErrorOut, "description": "No questions available or generatable"},
        502: {"model": ErrorOut},
    },
)
async def create_session(
    payload: PracticeSessionIn, session: AsyncSession = Depends(get_session)
) -> PracticeSessionOut:
    row = await practice_service.create_session(session, payload)
    return PracticeSessionOut.from_model(row)


@router.get(
    "/sessions/{session_id}",
    response_model=PracticeSessionOut,
    summary="Resume a practice session",
    responses={404: {"model": ErrorOut}},
)
async def get_session_detail(
    session_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PracticeSessionOut:
    row = await practice_service.get_session(session, session_id)
    return PracticeSessionOut.from_model(row)


@router.get(
    "/sessions/{session_id}/reveal/{question_id}",
    response_model=RevealOut,
    summary="Reveal the answer and explanation for one question",
    responses={404: {"model": ErrorOut}},
)
async def reveal(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RevealOut:
    question = await practice_service.reveal(session, session_id, question_id)
    return RevealOut(
        question_id=question.id,
        answer=question.answer,
        explanation=question.explanation or "",
    )
