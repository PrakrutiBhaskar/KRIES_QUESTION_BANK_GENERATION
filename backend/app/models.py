"""
ORM models — a direct translation of docs/db-schema.md.

Deviations from the doc are deliberate and noted inline; there are only two:
  * portable column types so the suite can run on SQLite while production
    stays on PostgreSQL (ADR 4), and
  * `questions.is_active` for soft deletes, so DELETE /questions/{id} doesn't
    orphan rows in `paper_questions` / `practice_session_questions`.

Enum values are persisted as the exact strings in the shared Question
contract ("MCQ" / "Short" / "Long", "easy" / "medium" / "hard"), so a row
round-trips into Module A's pydantic models without a mapping layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from generation_engine.schemas import Difficulty, QuestionType

from .db import Base

# --- Portable column types -------------------------------------------------
# db-schema.md specifies jsonb / text[]; those are used on PostgreSQL and
# degrade to JSON on SQLite so tests can run without a live Postgres.
JSONBType = JSON().with_variant(JSONB, "postgresql")
TagsType = JSON().with_variant(ARRAY(Text), "postgresql")


def _enum(python_enum, name: str) -> SAEnum:
    """Native PG enum that stores the contract's string values, not the
    Python member names (MCQ/Short/Long, not MCQ/SHORT/LONG)."""
    return SAEnum(
        python_enum,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        native_enum=True,
        validate_strings=True,
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Constrained to the five subjects in the shared contract. Stored as text
    # (not an enum) because db-schema.md says text, and because adding a
    # subject post-MVP shouldn't need a migration on an enum type.
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    grade_range: Mapped[str] = mapped_column(Text, nullable=False, default="7-9")

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="subject", cascade="all, delete-orphan", lazy="selectin"
    )


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        # Chapter names are unique within a subject — this is what makes
        # get-or-create on the generate path safe under concurrency.
        UniqueConstraint("subject_id", "name", name="uq_chapters_subject_name"),
        Index("ix_chapters_subject_order", "subject_id", "order_index"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    subject: Mapped[Subject] = relationship(back_populates="chapters", lazy="joined")


class Question(Base, TimestampMixin):
    __tablename__ = "questions"
    __table_args__ = (
        # db-schema.md: composite index for fast filtering.
        Index(
            "ix_questions_filter",
            "subject_id",
            "chapter_id",
            "type",
            "grade",
            "marks",
            "difficulty",
        ),
        Index("ix_questions_topic", "topic"),
        CheckConstraint("grade IN (7, 8, 9)", name="ck_questions_grade"),
        CheckConstraint("marks IN (1, 2, 3, 5)", name="ck_questions_marks"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[QuestionType] = mapped_column(
        _enum(QuestionType, "question_type"), nullable=False
    )
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str] | None] = mapped_column(JSONBType, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    marks: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(
        _enum(Difficulty, "difficulty"), nullable=False
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(TagsType, nullable=False, default=list)

    # Soft delete: DELETE /questions/{id} flips this rather than removing the
    # row, so papers and practice sessions that already reference the question
    # stay intact. Every read path filters on it.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )

    # `content_hash` backs the duplicate guard on insert — see
    # services/questions.py. Module A already de-duplicates within a batch;
    # this catches collisions across batches.
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    subject: Mapped[Subject] = relationship(lazy="joined")
    chapter: Mapped[Chapter] = relationship(lazy="joined")


class Paper(Base, TimestampMixin):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    total_marks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Nullable until auth lands (ADR 5). No FK to `users` yet because the
    # table doesn't exist in the MVP migration; the column is here so adding
    # the constraint later is a one-line migration, not a rewrite.
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    subject: Mapped[Subject] = relationship(lazy="joined")
    items: Mapped[list["PaperQuestion"]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperQuestion.order_index",
        lazy="selectin",
    )


class PaperQuestion(Base):
    __tablename__ = "paper_questions"
    __table_args__ = (
        UniqueConstraint("paper_id", "question_id", name="uq_paper_questions"),
        Index("ix_paper_questions_order", "paper_id", "order_index"),
    )

    # db-schema.md lists no surrogate key for the join tables; a composite PK
    # on (paper_id, question_id) expresses the same thing and makes the
    # "same question twice in one paper" case impossible by construction.
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), primary_key=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    marks_override: Mapped[int | None] = mapped_column(Integer, nullable=True)

    paper: Mapped[Paper] = relationship(back_populates="items")
    question: Mapped[Question] = relationship(lazy="joined")

    @property
    def effective_marks(self) -> int:
        return self.marks_override if self.marks_override is not None else self.question.marks


class PracticeSession(Base, TimestampMixin):
    __tablename__ = "practice_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    subject: Mapped[Subject] = relationship(lazy="joined")
    chapter: Mapped[Chapter] = relationship(lazy="joined")
    items: Mapped[list["PracticeSessionQuestion"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PracticeSessionQuestion.order_index",
        lazy="selectin",
    )


class PracticeSessionQuestion(Base):
    __tablename__ = "practice_session_questions"
    __table_args__ = (
        Index("ix_practice_session_questions_order", "session_id", "order_index"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), primary_key=True
    )
    # Not in db-schema.md's column list, but the practice set has to come back
    # in a stable order across reloads or the student sees questions shuffle.
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revealed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )

    session: Mapped[PracticeSession] = relationship(back_populates="items")
    question: Mapped[Question] = relationship(lazy="joined")
