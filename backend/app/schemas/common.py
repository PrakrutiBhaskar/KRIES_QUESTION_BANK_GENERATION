"""
Response shapes shared across routers.

`QuestionOut` is the wire form of the shared Question object in
api-contract.md. Note that it carries `subject` and `chapter` as *names*,
not the `subject_id` / `chapter_id` foreign keys the database uses — the
shared contract is name-based, and the frontend never sees our surrogate
keys. `from_model` is the single place that translation happens.
"""
from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from generation_engine.schemas import Difficulty, QuestionType, Subject

T = TypeVar("T")


class QuestionOut(BaseModel):
    """The shared Question object, as returned by every endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: Subject
    chapter: str
    type: QuestionType
    grade: int
    text: str
    options: list[str] | None = None
    answer: str
    explanation: str = ""
    marks: int
    difficulty: Difficulty
    topic: str = ""
    tags: list[str] = Field(default_factory=list)

    @classmethod
    def from_model(cls, row) -> "QuestionOut":
        return cls(
            id=row.id,
            subject=Subject(row.subject.name),
            chapter=row.chapter.name,
            type=row.type,
            grade=row.grade,
            text=row.text,
            options=row.options,
            answer=row.answer,
            explanation=row.explanation or "",
            marks=row.marks,
            difficulty=row.difficulty,
            topic=row.topic or "",
            tags=list(row.tags or []),
        )


class MaskedQuestionOut(BaseModel):
    """
    Practice-mode view of a question: everything except `answer` and
    `explanation`.

    This is a separate model rather than `QuestionOut` with the fields blanked
    out, so the answer key can't leak through a serialization mistake — the
    fields don't exist on the model at all. (test-plan.md Section 2:
    "answers withheld until reveal".)
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: Subject
    chapter: str
    type: QuestionType
    grade: int
    text: str
    options: list[str] | None = None
    marks: int
    difficulty: Difficulty
    topic: str = ""
    tags: list[str] = Field(default_factory=list)
    revealed: bool = False

    @classmethod
    def from_model(cls, row, *, revealed: bool = False) -> "MaskedQuestionOut":
        return cls(
            id=row.id,
            subject=Subject(row.subject.name),
            chapter=row.chapter.name,
            type=row.type,
            grade=row.grade,
            text=row.text,
            options=row.options,
            marks=row.marks,
            difficulty=row.difficulty,
            topic=row.topic or "",
            tags=list(row.tags or []),
            revealed=revealed,
        )


class Page(BaseModel, Generic[T]):
    """Pagination envelope for GET /questions (api-contract.md Section 2)."""

    results: list[T]
    total: int
    page: int
    page_size: int


class ErrorOut(BaseModel):
    """Documented only — produced by the handlers in errors.py."""

    error: str
    detail: str
