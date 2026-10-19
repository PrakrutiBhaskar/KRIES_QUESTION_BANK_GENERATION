"""
Request bodies, exactly as documented in api-contract.md.

Where a field isn't in the contract it's optional with a safe default, so
existing callers keep working: `refresh` on /generate is the only one.
The owner of a paper or practice session is taken from the bearer token, never
from the request body.
"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import MarksSplitPart

from generation_engine.schemas import (
    VALID_GRADES,
    VALID_MARKS_BY_TYPE,
    Difficulty,
    QuestionType,
    Subject,
)


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

    # Not in the contract. Write the questions about figures from the shared figure
    # library (see POST /figures): the model is given each figure's caption,
    # topic and labelled parts as text and every question comes back with its
    # figure attached. `use_figures` picks the library figures for this subject
    # and chapter; `figure_ids` names exact ones and implies `use_figures`.
    use_figures: bool = False
    figure_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)

    # Not in the contract. Let the server decide, at random, how many of these
    # questions are diagram-based (and which ones): some are written about figures
    # from the library, the rest are theory. A chapter with no library figure is
    # all theory. Ignored when `use_figures` / `figure_ids` is set.
    mix_figures: bool = False

    @field_validator("figure_ids")
    @classmethod
    def figure_ids_unique(cls, v: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if v is not None and len(set(v)) != len(v):
            raise ValueError("figure_ids must not contain duplicates")
        return v

    @property
    def wants_figures(self) -> bool:
        return self.use_figures or bool(self.figure_ids)

    @field_validator("chapter")
    @classmethod
    def chapter_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class VerifyIn(BaseModel):
    """POST /questions/verify — check the answer keys of stored questions."""

    model_config = ConfigDict(extra="forbid")

    question_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class QuestionIn(BaseModel):
    """POST /questions — a question written by hand (not generated)."""

    model_config = ConfigDict(extra="forbid")

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

    `answer` is editable. Because a hand-edited key has not been checked, any
    edit to the text, options or answer resets the question's verification
    to "unverified" (see services/questions.update_question); "Verify
    answers" can then be run on it again.
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
    # Attach a figure from the library, or send null to detach it.
    figure_id: uuid.UUID | None = None
    answer_figure_id: uuid.UUID | None = None
    # How the marks are split across the answer key, e.g. Diagram 2 + Explanation 3.
    # Must add up to the question's marks. Send null to go back to the automatic split.
    marks_split: list[MarksSplitPart] | None = Field(default=None, max_length=6)

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("must not be blank")
        return v.strip() if v is not None else None


class ExportIn(BaseModel):
    """
    POST /export/{paper_id} — optional body.

    The whole body is optional, and so is every field in it, so existing
    callers that POST with no body keep getting the full paper with its
    answer key. Send `include_answer_key: false` for a question-paper-only PDF
    (the one you hand to students).
    """

    model_config = ConfigDict(extra="forbid")

    include_answer_key: bool = True
    # "pdf" (default, the historical behaviour) or "docx" for an editable Word file.
    format: Literal["pdf", "docx"] = "pdf"


class FigurePatch(BaseModel):
    """PATCH /figures/{id} — caption and metadata; re-upload to change the image.

    Only the fields sent change. Send `""` (or `[]` for labels) to clear one.
    Length and value rules (subject must be a known subject, at most 30 labels)
    are enforced by the figure service, which answers 400 with a clear message.
    """

    model_config = ConfigDict(extra="forbid")

    caption: str | None = Field(default=None, max_length=300)
    subject: str | None = None
    chapter: str | None = None
    topic: str | None = None
    labels: list[str] | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "FigurePatch":
        if not self.model_fields_set:
            raise ValueError("send at least one of caption, subject, chapter, topic, labels")
        return self


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
    # Used only when this question is newly added to the paper (for example an
    # edited copy replacing the original); questions already in the paper keep
    # the section they have.
    section: str | None = None

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

    @field_validator("chapter")
    @classmethod
    def chapter_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


# --- blueprint papers --------------------------------------------------------

# A blueprint is the teacher's spec for a board-style paper: how many marks each
# section is worth (and what kind of question fills it), and how the paper's
# marks are split across chapters. The server turns it into a concrete list of
# questions — see services/blueprint.py.
MAX_BLUEPRINT_CHAPTERS = 12
MAX_BLUEPRINT_SECTIONS = 8
# Each question may mean an LLM call's worth of work and the request is one
# long transaction, so the size of a single paper is capped.
MAX_BLUEPRINT_QUESTIONS = 100

SectionDifficulty = Literal["easy", "medium", "hard", "mixed"]


class BlueprintChapterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # Share of the paper's total marks, in percent.
    weightage: float = Field(gt=0, le=100)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class BlueprintSectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    type: QuestionType
    marks_per_question: int
    # What the whole section is worth. The question count is derived:
    # total_marks / marks_per_question.
    total_marks: int = Field(gt=0)
    difficulty: SectionDifficulty = "medium"

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @model_validator(mode="after")
    def check_marks(self) -> "BlueprintSectionIn":
        allowed = VALID_MARKS_BY_TYPE[self.type]
        if self.marks_per_question not in allowed:
            raise ValueError(
                f'section "{self.name}": {self.type.value} questions must use marks '
                f"in {sorted(allowed)}, got {self.marks_per_question}"
            )
        if self.total_marks % self.marks_per_question:
            raise ValueError(
                f'section "{self.name}": {self.total_marks} marks is not a whole number '
                f"of {self.marks_per_question}-mark questions"
            )
        return self

    @property
    def question_count(self) -> int:
        return self.total_marks // self.marks_per_question


class BlueprintIn(BaseModel):
    """POST /papers/blueprint and POST /papers/blueprint/preview."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    subject: Subject
    grade: int
    chapters: list[BlueprintChapterIn] = Field(
        min_length=1, max_length=MAX_BLUEPRINT_CHAPTERS
    )
    sections: list[BlueprintSectionIn] = Field(
        min_length=1, max_length=MAX_BLUEPRINT_SECTIONS
    )
    # Same meaning as on /generate: skip stored questions and write new ones.
    refresh: bool = False

    @field_validator("grade")
    @classmethod
    def grade_valid(cls, v: int) -> int:
        if v not in VALID_GRADES:
            raise ValueError(f"must be one of {sorted(VALID_GRADES)}")
        return v

    @field_validator("title")
    @classmethod
    def title_clean(cls, v: str | None) -> str | None:
        return v.strip() or None if v is not None else None

    @model_validator(mode="after")
    def check_blueprint(self) -> "BlueprintIn":
        names = [c.name.lower() for c in self.chapters]
        if len(set(names)) != len(names):
            raise ValueError("chapters must not repeat")
        section_names = [s.name.lower() for s in self.sections]
        if len(set(section_names)) != len(section_names):
            raise ValueError("section names must be unique")

        total_weight = sum(c.weightage for c in self.chapters)
        if abs(total_weight - 100) > 0.01:
            raise ValueError(
                f"chapter weightage must add up to 100%, got {total_weight:g}%"
            )

        total_questions = sum(s.question_count for s in self.sections)
        if total_questions > MAX_BLUEPRINT_QUESTIONS:
            raise ValueError(
                f"a paper may have at most {MAX_BLUEPRINT_QUESTIONS} questions, "
                f"this blueprint has {total_questions}"
            )
        return self

    @property
    def total_marks(self) -> int:
        return sum(s.total_marks for s in self.sections)


class SeedChapterIn(BaseModel):
    """One chapter to add to the syllabus, with optional sub-topics."""

    model_config = ConfigDict(extra="forbid")

    name: str
    topics: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = " ".join((v or "").split())
        if not v:
            raise ValueError("a chapter needs a name")
        if len(v) > 200:
            raise ValueError("a chapter name can be at most 200 characters")
        return v

    @field_validator("topics")
    @classmethod
    def clean_topics(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for t in v:
            t = " ".join((t or "").split())
            if t and t.casefold() not in {x.casefold() for x in out}:
                if len(t) > 200:
                    raise ValueError("a topic can be at most 200 characters")
                out.append(t)
        return out


class SeedSyllabusIn(BaseModel):
    """POST /syllabus/seed: add chapters to one subject's syllabus for one grade."""

    model_config = ConfigDict(extra="forbid")

    subject: Subject
    grade: int = Field(ge=7, le=9)
    chapters: list[SeedChapterIn] = Field(min_length=1, max_length=100)
