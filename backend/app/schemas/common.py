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
from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_serializer
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable

from generation_engine.schemas import Difficulty, QuestionType, Subject

from ..config import settings

T = TypeVar("T")


class FigureOut(BaseModel):
    """A diagram attached to a question.

    `url` is a path under the API prefix. It needs the bearer token like every
    other route, so a client shows it by fetching the bytes with its
    Authorization header (an <img src> alone cannot send one).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    caption: str = ""
    mime: str
    width: int
    height: int
    size_bytes: int
    url: str
    created_at: datetime | None = None

    @classmethod
    def from_model(cls, row) -> "FigureOut":
        return cls(
            id=row.id,
            caption=row.caption or "",
            mime=row.mime,
            width=row.width,
            height=row.height,
            size_bytes=row.size_bytes,
            url=f"{settings.api_prefix}/figures/{row.id}/file",
            created_at=getattr(row, "created_at", None),
        )


# Roles that may see a figure's generation metadata (subject, chapter, topic, labels).
FIGURE_METADATA_ROLES = ("Admin", "Teacher")


class FigureDetailOut(FigureOut):
    """A figure as the figure library shows it: the image info plus its metadata.

    The metadata is what question generation works from. It is filled in for
    administrators (who manage the library) and teachers (who choose figures to
    write questions about). The labelled parts are effectively an answer key
    ("A: nucleus"), so they are never sent along with a question (that would
    hand practice-mode students the answers) and never shown to students.
    """

    subject: str | None = None
    chapter: str | None = None
    topic: str = ""
    labels: list[str] = Field(default_factory=list)

    @classmethod
    def from_model(cls, row, *, viewer_role: str | None = None) -> "FigureDetailOut":  # type: ignore[override]
        base = FigureOut.from_model(row).model_dump()
        if viewer_role not in FIGURE_METADATA_ROLES:
            return cls(**base)
        return cls(
            **base,
            subject=row.subject,
            chapter=row.chapter,
            topic=row.topic or "",
            labels=list(row.labels or []),
        )


_FIGURE_KEYS = ("figure", "answer_figure")


def _drop_empty_figures(data: dict) -> dict:
    """Leave `figure` / `answer_figure` out of the JSON when there is none.

    The shared Question contract (api-contract.md Section 2) has a fixed set of
    keys. Figures are an optional extension, so a question without one is
    serialised exactly as it was before figures existed, and existing clients
    never see a key they did not expect.
    """
    for key in _FIGURE_KEYS:
        if key in data and data[key] is None:
            del data[key]
    return data


def _figure_of(row, name: str) -> "FigureOut | None":
    """`row.figure` / `row.answer_figure` as FigureOut.

    Reads the relationship only if it is already loaded: touching an unloaded
    one inside async code would raise MissingGreenlet, and a freshly generated
    row (which never has a figure) is exactly that case.
    """
    try:
        if name in sa_inspect(row).unloaded:
            return None
    except NoInspectionAvailable:  # not an ORM row (e.g. a test double)
        pass
    figure = getattr(row, name, None)
    return FigureOut.from_model(figure) if figure is not None else None


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
    # Answer-key check: "verified" (confirmed by a rule or an independent AI
    # pass), "unverified" (could not be checked) or "flagged" (looked wrong).
    verification_status: Literal["verified", "unverified", "flagged"] = "unverified"
    verification_note: str | None = None
    # Optional diagrams: `figure` prints with the question, `answer_figure`
    # only in the answer key.
    figure: FigureOut | None = None
    answer_figure: FigureOut | None = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        return _drop_empty_figures(handler(self))

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
            verification_status=row.verification_status or "unverified",
            verification_note=row.verification_note,
            figure=_figure_of(row, "figure"),
            answer_figure=_figure_of(row, "answer_figure"),
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
    # The question's own diagram is part of the question; the answer-key
    # figure is deliberately absent here (see RevealOut).
    figure: FigureOut | None = None
    revealed: bool = False

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        return _drop_empty_figures(handler(self))

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
            figure=_figure_of(row, "figure"),
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
