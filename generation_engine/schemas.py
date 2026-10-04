"""
Shared data contract — mirrors the `Question` object defined in
project-context.md / spec.md / api-contract.md exactly, plus the
`GenerationRequest` shape used by `POST /generate`.

This is the single source of truth all three modules (Generation, Backend,
Frontend) are meant to build against.
"""
from __future__ import annotations

import re
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
    FILL = "Fill"  # fill in the blank
    MATCH = "Match"  # match the following


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
# - Fill in the blank is a 1-mark item with exactly one blank.
# - Match the following is one mark per pair, so a 3-mark question has 3 pairs
#   and a 5-mark question has 5 (the mark scale has no 4).
VALID_MARKS_BY_TYPE = {
    QuestionType.MCQ: {1},
    QuestionType.SHORT: {1, 2, 3},
    QuestionType.LONG: {5},
    QuestionType.FILL: {1},
    QuestionType.MATCH: {3, 5},
}

# ---------------------------------------------------------------------------
# Fill-in-the-blank and match-the-following shapes
# ---------------------------------------------------------------------------

# A blank is a run of three or more underscores.
BLANK_RE = re.compile(r"_{3,}")

# Column A lines inside a Match question's `text`: "1. item" or "1) item".
_MATCH_LEFT_LINE_RE = re.compile(r"^\s*(\d{1,2})\s*[.)]\s+(\S.*?)\s*$", re.MULTILINE)
# One pair inside a Match answer key: "1-C", "2 - a", "3: B", "4 = D".
_MATCH_ANSWER_PAIR_RE = re.compile(r"(\d{1,2})\s*[-\u2013\u2014:=]+>?\s*\(?([A-Za-z])\)?")

MATCH_LETTERS = "ABCDEFGHIJ"


def count_blanks(text: str) -> int:
    return len(BLANK_RE.findall(text or ""))


def match_left_items(text: str) -> list[str]:
    """Column A of a Match question: the numbered lines in `text`, in order.

    Returns [] unless the numbers run 1, 2, 3 ... with no gaps, so a stray
    numbered line in the stem cannot be mistaken for a column entry.
    """
    found = _MATCH_LEFT_LINE_RE.findall(text or "")
    if [int(n) for n, _ in found] != list(range(1, len(found) + 1)):
        return []
    return [item for _, item in found]


def parse_match_answer(answer: str) -> dict[int, str] | None:
    """{1: "C", 2: "A", ...} from "1-C, 2-A, ...", or None if it is not just pairs.

    Anything left over once the pairs are removed (other than separators)
    makes the answer unparseable, so prose such as "1 goes with C because ..."
    is rejected instead of half-read.
    """
    pairs = _MATCH_ANSWER_PAIR_RE.findall(answer or "")
    if not pairs:
        return None
    leftover = _MATCH_ANSWER_PAIR_RE.sub("", answer)
    if re.sub(r"[\s,;.]+", "", leftover):
        return None
    out: dict[int, str] = {}
    for n, letter in pairs:
        if int(n) in out:
            return None  # the same item matched twice
        out[int(n)] = letter.upper()
    return out


def format_match_answer(mapping: dict[int, str]) -> str:
    """The canonical answer-key text: "1-C, 2-A, 3-B"."""
    return ", ".join(f"{n}-{mapping[n]}" for n in sorted(mapping))


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
        elif self.type == QuestionType.MATCH:
            self._check_match_shape()
        else:
            if self.options:
                raise ValueError(
                    f"{self.type.value} questions must not carry MCQ options"
                )
            if self.type == QuestionType.FILL:
                blanks = count_blanks(self.text)
                if blanks != 1:
                    raise ValueError(
                        "Fill questions must contain exactly one blank "
                        f"(a run of underscores such as _____), found {blanks}"
                    )

        expected_marks = VALID_MARKS_BY_TYPE[self.type]
        if self.marks not in expected_marks:
            raise ValueError(
                f"{self.type.value} questions must use marks in "
                f"{sorted(expected_marks)}, got {self.marks}"
            )
        return self

    def _check_match_shape(self) -> None:
        """Match: numbered Column A in `text`, lettered Column B in `options`.

        One mark per pair, so the number of pairs equals the marks. The answer
        is a strict one-to-one mapping ("1-C, 2-A, 3-B"): every number once,
        every option letter once.
        """
        n = self.marks
        left = match_left_items(self.text)
        if len(left) != n:
            raise ValueError(
                f"Match questions need {n} numbered items (1., 2., ...) in the "
                f"text for {n} marks, found {len(left)}"
            )
        options = [o.strip() for o in (self.options or [])]
        if len(options) != n or any(not o for o in options):
            raise ValueError(f"Match questions must have exactly {n} options (Column B)")
        if len({o.lower() for o in options}) != n:
            raise ValueError("Match options must not contain duplicates")
        mapping = parse_match_answer(self.answer)
        if mapping is None:
            raise ValueError(
                'Match answer must be pairs such as "1-C, 2-A, 3-B" and nothing else'
            )
        letters = set(MATCH_LETTERS[:n])
        if set(mapping) != set(range(1, n + 1)) or set(mapping.values()) != letters:
            raise ValueError(
                f"Match answer must pair every item 1-{n} with a different "
                f"option letter {MATCH_LETTERS[0]}-{MATCH_LETTERS[n - 1]}"
            )


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
    # Where to start walking the chapter's textbook passages. The backend sets
    # this to the number of questions already stored for the chapter so that
    # repeated generation moves through the WHOLE chapter instead of
    # re-covering the same passages. Ignored without an ingested textbook.
    coverage_offset: int = Field(default=0, ge=0)
    # Optional: stored figures to write questions about (text description only).
    # When set, every generated question must be about exactly one of them.
    figures: Optional[List[FigureContext]] = Field(default=None, max_length=20)

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
