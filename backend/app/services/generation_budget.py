"""
How many *new* questions a user may have written by the model.

Students can generate question banks and papers, but the question bank comes
first: `generation.generate_questions` always serves stored questions before it
asks the model for anything, and the model is only asked for the shortfall.
This module caps that shortfall for student accounts so the API is a fallback,
not the default:

  * per request  - STUDENT_MAX_NEW_QUESTIONS_PER_REQUEST
  * per UTC day  - STUDENT_MAX_NEW_QUESTIONS_PER_DAY

The daily figure needs no extra table: it is the number of questions this user
created today (`questions.created_by` / `created_at`). Teachers and
administrators get no budget (`None`) and are never limited.

A `GenerationBudget` is created once per request and shared by every
generation call inside it, so a paper that needs many groups of questions
spends one allowance, not one per group. The budget is charged *before* the
model is called, for the whole shortfall, so a request that cannot be paid for
is refused without spending anything.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..errors import GenerationAllowanceError
from ..models import Question

STUDENT_ROLE = "Student"


@dataclass
class GenerationBudget:
    remaining: int
    # True when today's allowance, not the per-request cap, is what limits this
    # request. Only changes the wording of the refusal.
    limited_by_day: bool = False

    def reserve(self, n: int) -> None:
        """Charge `n` new questions, or raise 429 without charging anything."""
        self.check(n)
        self.remaining -= max(n, 0)

    def check(self, n: int) -> None:
        """Raise 429 if `n` new questions would not fit; charges nothing."""
        if n <= 0:
            return
        if n > self.remaining:
            if self.limited_by_day:
                left = (
                    "none left" if self.remaining == 0 else f"{self.remaining} left"
                )
                raise GenerationAllowanceError(
                    f"The question bank doesn't have enough stored questions for this "
                    f"request, and today's allowance for new ones is nearly used "
                    f"({left}). Ask for fewer questions, pick a chapter with more "
                    "stored, or try again tomorrow."
                )
            raise GenerationAllowanceError(
                f"The question bank has too few stored questions for this request: "
                f"{n} new ones would be needed, but you can create at most "
                f"{self.remaining} at a time. Ask for fewer questions or pick a "
                "chapter that has more stored."
            )


def is_student(role: str | None) -> bool:
    return role == STUDENT_ROLE


async def _created_today(session: AsyncSession, user_id: uuid.UUID) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count = await session.scalar(
        select(func.count(Question.id)).where(
            Question.created_by == user_id,
            Question.created_at >= start,
        )
    )
    return int(count or 0)


async def budget_for(
    session: AsyncSession, *, user_id: uuid.UUID, role: str | None
) -> GenerationBudget | None:
    """The budget for this user's request; `None` means unlimited (teacher/admin)."""
    if not is_student(role):
        return None
    per_request = settings.student_max_new_per_request
    daily_left = max(settings.student_max_new_per_day - await _created_today(session, user_id), 0)
    return GenerationBudget(
        remaining=min(per_request, daily_left),
        limited_by_day=daily_left < per_request,
    )
