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

# Grades this engine is scoped to (spec.md Section 2: "Karnataka State Board,
# grades 7-9"). Selected per request rather than assumed, so prompts and
# validation stay in step with whatever the caller actually asked for.
VALID_GRADES = {7, 8, 9}

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


class FigureContext(BaseModel):
    """What the model is told about one stored figure (a text description only).

    The model never sees the image. It works from the caption and the list of
    labelled parts the teacher typed in, and the caller attaches `figure_id`
    itself, so the model cannot invent or mis-copy a figure reference.
    """

    id: str
    caption: str = ""
    labels: List[str] = Field(default_factory=list)
    topic: str = ""

    def describe(self) -> str:
        """One plain-text description, shared by the generation prompt and the verifier."""
        parts = []
        if self.caption.strip():
            parts.append(f"Caption: {self.caption.strip()}")
        if self.topic.strip():
            parts.append(f"Topic: {self.topic.strip()}")
        if self.labels:
            parts.append("Labelled parts: " + "; ".join(l.strip() for l in self.labels if l.strip()))
        return ". ".join(parts)


def figure_ref_map(figures: Optional[List[FigureContext]]) -> dict[str, FigureContext]:
    """Short references the model uses instead of real ids: F1, F2, ... in list order.

    A short ref is far less likely to be mis-copied than a UUID, and it means
    the model can only ever name a figure the caller actually offered.
    """
    return {f"F{i}": fig for i, fig in enumerate(figures or [], start=1)}


class Question(BaseModel):
    """The shared Question object (api-contract.md)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    subject: Subject
    chapter: str
    type: QuestionType
    grade: int
    text: str
    options: Optional[List[str]] = None
    answer: str
    explanation: str = ""
    marks: int
    difficulty: Difficulty
    topic: str = ""
    tags: List[str] = Field(default_factory=list)
    # Filled in by the engine's answer-key verification (answer_verification.py):
    # "verified" | "unverified" | "flagged". None = never checked.
    verification_status: Optional[str] = None
    verification_note: Optional[str] = None
    # Set when the question was written about one of the figures in
    # `GenerationRequest.figures`. The id is attached by the engine from the
    # model's short reference ("F1"), never taken from the model verbatim.
    figure_id: Optional[str] = None
    # The text description the question was written from. Only used to give the
    # answer-key verifier the same context; never serialised or stored.
    figure_context: Optional[str] = Field(default=None, exclude=True)

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

    @field_validator("grade")
    @classmethod
    def grade_in_range(cls, v: int) -> int:
        if v not in VALID_GRADES:
            raise ValueError(f"grade must be one of {sorted(VALID_GRADES)}, got {v}")
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
    grade: int
    marks: int
    difficulty: Difficulty
    count: int = Field(ge=1, le=25)
    topic: Optional[str] = None  # optional narrowing hint fed into the prompt
    # Optional: stored figures to write questions about (text description only).
    # When set, every generated question must be about exactly one of them.
    figures: Optional[List[FigureContext]] = Field(default=None, max_length=20)
    # Where to start walking the chapter's textbook passages. The backend sets
    # this to the number of questions already stored for the chapter so that
    # repeated generation moves through the WHOLE chapter instead of
    # re-covering the same passages. Ignored without an ingested textbook.
    coverage_offset: int = Field(default=0, ge=0)

    @field_validator("chapter")
    @classmethod
    def chapter_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("chapter must not be blank")
        return v.strip()

    # NOTE: grade range is deliberately NOT enforced here (mirrors `marks`,
    # which also isn't schema-validated on this class). An out-of-range grade
    # should surface as a 400 InvalidRequestError via
    # validate_request_combination(), not a raw pydantic ValidationError at
    # construction time — that's what api-contract.md's 400 case describes.
