"""Initial schema — subjects, chapters, questions, papers, practice sessions.

Implements docs/db-schema.md.

Revision ID: 0001
Revises:
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

QUESTION_TYPE = postgresql.ENUM(
    "MCQ", "Short", "Long", name="question_type", create_type=False
)
DIFFICULTY = postgresql.ENUM(
    "easy", "medium", "hard", name="difficulty", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        QUESTION_TYPE.create(bind, checkfirst=True)
        DIFFICULTY.create(bind, checkfirst=True)
        q_type = QUESTION_TYPE
        difficulty = DIFFICULTY
        options_type = postgresql.JSONB()
        tags_type = postgresql.ARRAY(sa.Text())
    else:  # SQLite / other — used by the test suite
        q_type = sa.Enum("MCQ", "Short", "Long", name="question_type")
        difficulty = sa.Enum("easy", "medium", "hard", name="difficulty")
        options_type = sa.JSON()
        tags_type = sa.JSON()

    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("grade_range", sa.Text(), nullable=False, server_default="7-9"),
    )

    op.create_table(
        "chapters",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "subject_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("subject_id", "name", name="uq_chapters_subject_name"),
    )
    op.create_index("ix_chapters_subject_order", "chapters", ["subject_id", "order_index"])

    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "subject_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("subjects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("chapters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("type", q_type, nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", options_type, nullable=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("marks", sa.Integer(), nullable=False),
        sa.Column("difficulty", difficulty, nullable=False),
        sa.Column("topic", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", tags_type, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("grade IN (7, 8, 9)", name="ck_questions_grade"),
        sa.CheckConstraint("marks IN (1, 2, 3, 5)", name="ck_questions_marks"),
    )
    # db-schema.md: composite index for fast filtering.
    op.create_index(
        "ix_questions_filter",
        "questions",
        ["subject_id", "chapter_id", "type", "grade", "marks", "difficulty"],
    )
    op.create_index("ix_questions_topic", "questions", ["topic"])
    op.create_index("ix_questions_content_hash", "questions", ["content_hash"])

    op.create_table(
        "papers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "subject_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("subjects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("total_marks", sa.Integer(), nullable=False, server_default="0"),
        # Nullable until auth lands (ADR 5); no FK yet because `users` doesn't
        # exist in the MVP.
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "paper_questions",
        sa.Column(
            "paper_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "question_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("marks_override", sa.Integer(), nullable=True),
        sa.UniqueConstraint("paper_id", "question_id", name="uq_paper_questions"),
    )
    op.create_index("ix_paper_questions_order", "paper_questions", ["paper_id", "order_index"])

    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "subject_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("subjects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("chapters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "practice_session_questions",
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("practice_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "question_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revealed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_practice_session_questions_order",
        "practice_session_questions",
        ["session_id", "order_index"],
    )


def downgrade() -> None:
    op.drop_table("practice_session_questions")
    op.drop_table("practice_sessions")
    op.drop_table("paper_questions")
    op.drop_table("papers")
    op.drop_table("questions")
    op.drop_table("chapters")
    op.drop_table("subjects")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        DIFFICULTY.drop(bind, checkfirst=True)
        QUESTION_TYPE.drop(bind, checkfirst=True)
