"""
Generation and question-bank endpoints.

  POST   /generate            api-contract.md Section 1
  POST   /questions/verify    check answer keys (the "Verify answers" button)
  GET    /generation/combinations   not in the contract; see docstring below
  GET    /questions           api-contract.md Section 2
  GET    /questions/{id}
  PATCH  /questions/{id}
  POST   /questions/{id}/copy   an editable copy of someone else's question
  POST   /questions             add a question you wrote yourself
  DELETE /questions/{id}
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.prompts import supported_combinations
from generation_engine.schemas import Difficulty, QuestionType, Subject

from ..db import get_session
from ..deps import get_current_user, require_editor, require_generator
from ..models import User
from ..schemas.common import auto_split_of, parts_of
from ..schemas import (
    CombinationOut,
    ErrorOut,
    GenerateIn,
    GenerateOut,
    MarksSplitOut,
    Page,
    QuestionIn,
    QuestionOut,
    QuestionPatch,
    VerifyIn,
    VerifyOut,
)
from ..services import generation as generation_service
from ..services.generation_budget import budget_for, is_student
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
    payload: GenerateIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GenerateOut:
    # Students use the stored questions first and the model only for what is
    # missing: they cannot force fresh generation, and what they may create is capped.
    if is_student(user.role) and payload.refresh:
        payload = payload.model_copy(update={"refresh": False})
    budget = await budget_for(session, user_id=user.id, role=user.role)
    questions, cached, generated, report = await generation_service.generate_questions(
        session, payload, user_id=user.id, budget=budget
    )
    return GenerateOut(
        questions=[QuestionOut.from_model(q) for q in questions],
        cached=cached,
        generated=generated,
        report=report,
    )


@router.post(
    "/questions/verify",
    response_model=VerifyOut,
    summary="Verify the answer keys of generated questions",
    description=(
        "Checks each question's answer key (rule checks, then an independent AI "
        "pass) and stores the result as `verification_status` / "
        "`verification_note`. Generation does not do this: it is a separate "
        "step, started by the \"Verify answers\" button."
    ),
    responses={
        404: {"model": ErrorOut, "description": "A question id does not exist"},
    },
)
async def verify_questions(
    payload: VerifyIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_generator),
) -> VerifyOut:
    rows = await generation_service.verify_questions(session, payload.question_ids)
    out = [QuestionOut.from_model(r) for r in rows]
    return VerifyOut(
        questions=out,
        verified=sum(q.verification_status == "verified" for q in out),
        unverified=sum(q.verification_status == "unverified" for q in out),
        flagged=sum(q.verification_status == "flagged" for q in out),
    )


@router.get(
    "/generation/combinations",
    response_model=list[CombinationOut],
    summary="List the (type, marks) combinations POST /generate accepts",
)
async def generation_combinations() -> list[CombinationOut]:
    """Not in api-contract.md — added so the frontend's generation-request
    screen can build its type/marks selectors from the same rule
    generation_engine.prompts.supported_combinations() actually enforces,
    instead of hardcoding a duplicate that can drift out of sync. Any
    (type, marks) pair not listed here gets a 400 from POST /generate.
    """
    marks_by_type: dict[QuestionType, list[int]] = {}
    for q_type, marks in supported_combinations():
        marks_by_type.setdefault(q_type, []).append(marks)
    return [
        CombinationOut(type=q_type, marks=sorted(marks))
        for q_type, marks in marks_by_type.items()
    ]


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


@router.get(
    "/questions/{question_id}/marks-split",
    response_model=MarksSplitOut,
    summary="The marks split an answer key prints, for the editor to start from",
    description=(
        "Returns the teacher's own split (null when there is none) and the "
        "automatic one the key would print instead. Teachers and administrators only."
    ),
    responses={403: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
async def get_marks_split(
    question_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
) -> MarksSplitOut:
    row = await question_service.get_question(session, question_id)
    auto = auto_split_of(row)
    return MarksSplitOut(
        marks=row.marks,
        marks_split=parts_of(row.marks_split),
        auto_marks_split=auto,
        editable=row.type.value in ("Short", "Long") and row.marks > 1,
    )


@router.patch(
    "/questions/{question_id}",
    response_model=QuestionOut,
    summary="Edit a question you generated",
    description=(
        "Wording, options, answer, explanation, difficulty and the marks split of "
        "the answer key. Teachers and administrators only."
    ),
    responses={
        400: {"model": ErrorOut},
        403: {"model": ErrorOut, "description": "Not a teacher/administrator, or someone else generated this question"},
        404: {"model": ErrorOut},
    },
)
async def patch_question(
    question_id: uuid.UUID,
    payload: QuestionPatch,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
) -> QuestionOut:
    row = await question_service.update_question(
        session,
        question_id,
        payload.model_dump(exclude_unset=True),
        user_id=user.id,
    )
    return QuestionOut.from_model(row)


@router.post(
    "/questions",
    response_model=QuestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a question you wrote yourself",
    description=(
        "Stores a hand-written question (and its answer and explanation) after the "
        "same checks a generated one gets. It is `unverified` until someone runs "
        "**Verify answers** on it. Teachers and administrators only."
    ),
    responses={400: {"model": ErrorOut}, 403: {"model": ErrorOut}},
)
async def create_question(
    payload: QuestionIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
) -> QuestionOut:
    row = await question_service.create_manual_question(session, payload, user_id=user.id)
    return QuestionOut.from_model(row)


@router.post(
    "/questions/{question_id}/copy",
    response_model=QuestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Make your own editable copy of a question",
    description=(
        "Only the person who generated a question can edit it. For any other "
        "question this makes a copy owned by the caller, which they can then "
        "edit with `PATCH /questions/{id}`. The original is not changed."
    ),
    responses={404: {"model": ErrorOut}},
)
async def copy_question(
    question_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
) -> QuestionOut:
    row = await question_service.copy_question(session, question_id, user_id=user.id)
    return QuestionOut.from_model(row)


@router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Discard a question",
    description=(
        "Removes a question you generated from the shared pool. For a question "
        "someone else generated this succeeds without changing anything, so "
        "the caller can drop it from their own draft without affecting others."
    ),
    responses={404: {"model": ErrorOut}},
)
async def delete_question(
    question_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
) -> Response:
    await question_service.delete_question(session, question_id, user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
