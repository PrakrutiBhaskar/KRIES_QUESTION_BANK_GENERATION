"""
Shared data contract — mirrors the `Question` object defined in
project-context.md / spec.md / api-contract.md exactly, plus the
`GenerationRequest` shape used by `POST /generate`.

This is the single source of truth all three modules (Generation, Backend,
Frontend) are meant to build against.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Subject(str, Enum):
    MATH = "Math"
    SCIENCE = "Science"
    SOCIAL_SCIENCE = "Social Science"
    ENGLISH = "English"
    KANNADA = "Kannada"


class QuestionType(str, Enum):
    MCQ = "MCQ"
    SHORT = "Short"
    LONG = "Long"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# Mark values allowed system-wide (spec.md Section 4: marks: 1 | 2 | 3 | 5)
VALID_MARKS = {1, 2, 3, 5}

# Which marks are valid for which question type.
#
# - MCQ is fixed at 1 mark (spec.md Section 7: "MCQs ... typically fixed at
#   1 mark").
# - Short answer covers the 1-, 2- and 3-mark formats. The 1-mark descriptive
#   case is explicitly required by spec.md Section 7 — the mark-scheme table
#   gives non-MCQ 1-mark examples for every subject ("What is the SI unit of
#   force?" -> Newton), and Module A lists "1 mark -> direct one-line answer,
#   no explanation" as a bullet separate from the MCQ rule.
# - Long answer is the 5-mark, exam-response format (prompt-library.md).
VALID_MARKS_BY_TYPE = {
    QuestionType.MCQ: {1},
    QuestionType.SHORT: {1, 2, 3},
    QuestionType.LONG: {5},
}


class Question(BaseModel):
    """The shared Question object (api-contract.md)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    subject: Subject
    chapter: str
    type: QuestionType
    text: str
    options: Optional[List[str]] = None
    answer: str
    explanation: str = ""
    marks: int
    difficulty: Difficulty
    topic: str = ""
    tags: List[str] = Field(default_factory=list)

    @field_validator("chapter", "text", "answer")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("marks")
    @classmethod
    def marks_in_range(cls, v: int) -> int:
        if v not in VALID_MARKS:
            raise ValueError(f"marks must be one of {sorted(VALID_MARKS)}, got {v}")
        return v

    @model_validator(mode="after")
    def check_type_specific_shape(self) -> "Question":
        if self.type == QuestionType.MCQ:
            if not self.options or len(self.options) != 4:
                raise ValueError("MCQ questions must have exactly 4 options")
            if len(set(o.strip().lower() for o in self.options)) != 4:
                raise ValueError("MCQ options must not contain duplicates")
            if self.answer.strip() not in [o.strip() for o in self.options]:
                raise ValueError("MCQ answer must be one of the provided options")
            if not self.explanation or not self.explanation.strip():
                raise ValueError(
                    "MCQ questions require a 1-line justification (explanation)"
                )
            if self.marks != 1:
                raise ValueError("MCQ questions must be worth 1 mark")
        else:
            if self.options:
                raise ValueError(
                    f"{self.type.value} questions must not carry MCQ options"
                )

        expected_marks = VALID_MARKS_BY_TYPE[self.type]
        if self.marks not in expected_marks:
            raise ValueError(
                f"{self.type.value} questions must use marks in "
                f"{sorted(expected_marks)}, got {self.marks}"
            )
        return self


class GenerationRequest(BaseModel):
    """Mirrors the POST /generate request body in api-contract.md."""

    subject: Subject
    chapter: str
    type: QuestionType
    marks: int
    difficulty: Difficulty
    count: int = Field(ge=1, le=25)
    topic: Optional[str] = None  # optional narrowing hint fed into the prompt

    @field_validator("chapter")
    @classmethod
    def chapter_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("chapter must not be blank")
        return v.strip()
