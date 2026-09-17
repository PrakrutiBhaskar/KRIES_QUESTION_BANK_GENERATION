"""Response bodies for papers, practice sessions, export and syllabus data."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from generation_engine.schemas import Subject

from .common import MaskedQuestionOut, QuestionOut


class GenerateOut(BaseModel):
    """POST /generate — the contract's `{"questions": [...]}`.

    `report` is the diagnostic counter set from Module A's GenerationReport
    (attempts made, items dropped and why). exceptions.py suggests logging it
    rather than returning it; it's logged *and* returned here because the
    generation screen in ui-wireframes.md has to explain a partially-cached
    or retried batch to the user. `cached` says how many of the returned
    questions came from storage rather than a fresh Groq call.
    """

    questions: list[QuestionOut]
    cached: int = 0
    generated: int = 0
    report: dict | None = None


class PaperQuestionOut(BaseModel):
    order_index: int
    marks: int  # effective marks: marks_override if set, else the question's
    marks_override: int | None = None
    question: QuestionOut


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    subject: Subject
    total_marks: int
    user_id: uuid.UUID | None = None
    created_at: datetime
    questions: list[PaperQuestionOut]

    @classmethod
    def from_model(cls, paper) -> "PaperOut":
        return cls(
            id=paper.id,
            title=paper.title,
            subject=Subject(paper.subject.name),
            total_marks=paper.total_marks,
            user_id=paper.user_id,
            created_at=paper.created_at,
            questions=[
                PaperQuestionOut(
                    order_index=item.order_index,
                    marks=item.effective_marks,
                    marks_override=item.marks_override,
                    question=QuestionOut.from_model(item.question),
                )
                for item in sorted(paper.items, key=lambda i: i.order_index)
            ],
        )


class PracticeSessionOut(BaseModel):
    """
    POST /practice/sessions — questions come back masked (no answer key).
    """

    id: uuid.UUID
    subject: Subject
    chapter: str
    user_id: uuid.UUID | None = None
    created_at: datetime
    questions: list[MaskedQuestionOut]

    @classmethod
    def from_model(cls, session) -> "PracticeSessionOut":
        return cls(
            id=session.id,
            subject=Subject(session.subject.name),
            chapter=session.chapter.name,
            user_id=session.user_id,
            created_at=session.created_at,
            questions=[
                MaskedQuestionOut.from_model(item.question, revealed=item.revealed)
                for item in sorted(session.items, key=lambda i: i.order_index)
            ],
        )


class RevealOut(BaseModel):
    """GET /practice/sessions/{id}/reveal/{question_id}."""

    question_id: uuid.UUID
    answer: str
    explanation: str = ""


class ExportOut(BaseModel):
    """POST /export/{paper_id} — the contract's `{"download_url": "..."}`."""

    download_url: str
    filename: str
    size_bytes: int


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: Subject
    grade_range: str
    chapter_count: int = 0


class ChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    order_index: int
    question_count: int = 0
