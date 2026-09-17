"""
Practice mode (student flow).

The session stores *which* questions were drawn and whether each has been
revealed. Answers are never part of the session payload — they're fetched one
at a time through the reveal endpoint, which is what makes
"doesn't leak other answers" (test-plan.md Section 3) true at the API layer
rather than depending on the frontend to hide them.

Question selection prefers what's already in the bank. If the chapter is
thin, the shortfall is generated on demand (PRACTICE_GENERATE_SHORTFALL) so a
student picking a fresh chapter isn't handed an empty set.
"""
from __future__ import annotations

import random
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import QuestionType

from ..config import settings
from ..errors import NotFoundError, UnprocessableError
from ..models import PracticeSession, PracticeSessionQuestion, Question
from ..schemas.requests import GenerateIn, PracticeSessionIn
from . import generation as generation_service
from .syllabus import resolve_chapter

# Marks to request per type when generating a shortfall. MCQ is fixed at 1
# (schemas.VALID_MARKS_BY_TYPE); Short defaults to the 2-mark format and Long
# is only ever 5.
_DEFAULT_MARKS = {QuestionType.MCQ: 1, QuestionType.SHORT: 2, QuestionType.LONG: 5}


async def _stored_pool(
    session: AsyncSession, payload: PracticeSessionIn, chapter_id: uuid.UUID
) -> list[Question]:
    stmt = select(Question).where(
        Question.is_active.is_(True),
        Question.chapter_id == chapter_id,
        Question.grade == payload.grade,
    )
    if payload.type is not None:
        stmt = stmt.where(Question.type == payload.type)
    if payload.difficulty is not None:
        stmt = stmt.where(Question.difficulty == payload.difficulty)
    return list((await session.scalars(stmt)).all())


async def create_session(
    session: AsyncSession, payload: PracticeSessionIn
) -> PracticeSession:
    chapter = await resolve_chapter(session, payload.subject, payload.chapter)

    pool = await _stored_pool(session, payload, chapter.id)
    random.shuffle(pool)
    chosen = pool[: payload.count]

    shortfall = payload.count - len(chosen)
    if shortfall > 0 and settings.practice_generate_shortfall:
        q_type = payload.type or QuestionType.MCQ
        generated, _, _, _ = await generation_service.generate_questions(
            session,
            GenerateIn(
                subject=payload.subject,
                chapter=chapter.name,
                type=q_type,
                grade=payload.grade,
                marks=_DEFAULT_MARKS[q_type],
                difficulty=payload.difficulty or "medium",
                count=shortfall,
                refresh=True,  # the stored pool was already drained above
            ),
        )
        chosen_ids = {row.id for row in chosen}
        chosen.extend(row for row in generated if row.id not in chosen_ids)
        chosen = chosen[: payload.count]

    if not chosen:
        raise UnprocessableError(
            f'No questions available for {payload.subject.value} / '
            f'"{chapter.name}" matching that filter, and none could be generated.'
        )

    practice = PracticeSession(
        subject_id=chapter.subject_id,
        chapter_id=chapter.id,
        user_id=payload.user_id,
    )
    session.add(practice)
    await session.flush()

    for order, question in enumerate(chosen):
        session.add(
            PracticeSessionQuestion(
                session_id=practice.id, question_id=question.id, order_index=order
            )
        )
    await session.flush()
    await session.refresh(practice, attribute_names=["items", "subject", "chapter"])
    return practice


async def get_session(
    session: AsyncSession, session_id: uuid.UUID
) -> PracticeSession:
    row = await session.scalar(
        select(PracticeSession).where(PracticeSession.id == session_id)
    )
    if row is None:
        raise NotFoundError(f"Practice session {session_id} not found.")
    return row


async def reveal(
    session: AsyncSession, session_id: uuid.UUID, question_id: uuid.UUID
) -> Question:
    """
    Reveal one answer.

    The lookup is scoped to the (session, question) pair, so asking for a
    question that isn't in this session 404s rather than returning an answer
    from somewhere else in the bank.
    """
    await get_session(session, session_id)  # 404 for an unknown session

    item = await session.scalar(
        select(PracticeSessionQuestion).where(
            PracticeSessionQuestion.session_id == session_id,
            PracticeSessionQuestion.question_id == question_id,
        )
    )
    if item is None:
        raise NotFoundError(
            f"Question {question_id} is not part of session {session_id}."
        )

    item.revealed = True
    await session.flush()
    return item.question
