"""
Request bodies, exactly as documented in api-contract.md.

Where a field isn't in the contract it's optional with a safe default, so
existing callers keep working: `refresh` on /generate and `user_id` on
/papers and /practice/sessions are the only two.
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from generation_engine.schemas import Difficulty, QuestionType, Subject


class GenerateIn(BaseModel):
    """POST /generate (api-contract.md Section 1)."""

    model_config = ConfigDict(extra="forbid")

    subject: Subject
    chapter: str
    type: QuestionType
    grade: int
    marks: int
    difficulty: Difficulty
    count: int = Field(default=5, ge=1)
    topic: str | None = None

    # Not in the contract. Defaults to false, i.e. the cached/stored-reuse
    # path described in spec.md Module B. Set true to force fresh Groq calls.
    refresh: bool = False

    @field_validator("chapter")
    @classmethod
    def chapter_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class QuestionPatch(BaseModel):
    """
    PATCH /questions/{id} — teacher curation.

    Every field is optional; only what's sent is changed. `subject`, `chapter`
    and `grade` are deliberately NOT editable: moving a question between
    subjects would invalidate the marks/format rules it was generated and
    validated under. Re-generate instead.
    """

    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    options: list[str] | None = None
    answer: str | None = None
    explanation: str | None = None
    marks: int | None = None
    difficulty: Difficulty | None = None
    topic: str | None = None
    tags: list[str] | None = None

    @field_validator("text", "answer")
    @classmethod
    def not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("must not be blank")
        return v.strip() if v is not None else None


class PaperIn(BaseModel):
    """POST /papers (api-contract.md Section 3)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    subject: Subject
    question_ids: list[uuid.UUID] = Field(min_length=1)
    # The contract sends this, but the server is the authority: it's recomputed
    # from the questions. If the client's figure disagrees, that's a 400 rather
    # than a silent overwrite, so a stale frontend total surfaces immediately.
    total_marks: int | None = None
    user_id: uuid.UUID | None = None

    @field_validator("question_ids")
    @classmethod
    def no_duplicates(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(v)) != len(v):
            raise ValueError("question_ids must not contain duplicates")
        return v


class PaperItemPatch(BaseModel):
    """One row of the paper's question list, for reordering / marks override."""

    model_config = ConfigDict(extra="forbid")

    question_id: uuid.UUID
    order_index: int = Field(ge=0)
    marks_override: int | None = None

    @field_validator("marks_override")
    @classmethod
    def valid_marks(cls, v: int | None) -> int | None:
        if v is not None and v not in (1, 2, 3, 5):
            raise ValueError("marks_override must be one of 1, 2, 3, 5")
        return v


class PaperPatch(BaseModel):
    """
    PATCH /papers/{id} — reorder questions, override marks, rename.

    `questions`, when present, replaces the paper's whole question list. A
    partial list would leave the remaining questions' order ambiguous, so the
    frontend sends the full ordered set it's showing.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)
    questions: list[PaperItemPatch] | None = None

    @field_validator("questions")
    @classmethod
    def no_duplicates(cls, v):
        if v is not None:
            ids = [i.question_id for i in v]
            if len(set(ids)) != len(ids):
                raise ValueError("questions must not repeat a question_id")
        return v


class PracticeSessionIn(BaseModel):
    """POST /practice/sessions (api-contract.md Section 5)."""

    model_config = ConfigDict(extra="forbid")

    subject: Subject
    chapter: str
    type: QuestionType | None = None
    grade: int
    difficulty: Difficulty | None = None
    count: int = Field(default=10, ge=1, le=50)
    user_id: uuid.UUID | None = None

    @field_validator("chapter")
    @classmethod
    def chapter_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()
