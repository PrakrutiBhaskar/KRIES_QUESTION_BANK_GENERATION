"""Ownership: who generated each question, and indexes on the owner columns.

`papers.user_id` and `practice_sessions.user_id` already exist (nullable), so
this only adds `questions.created_by` and the lookup indexes. No foreign keys
are added: rows created before sign-in existed have a NULL owner, and any id a
client once sent in the request body may not match a real user.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None
# The app's startup schema sync may already have added these, so each step checks first.


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return insp.has_table(table) and column in {c["name"] for c in insp.get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return insp.has_table(table) and name in {i["name"] for i in insp.get_indexes(table)}


def _has_fk(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return insp.has_table(table) and name in {f["name"] for f in insp.get_foreign_keys(table)}


def upgrade() -> None:
    if not _has_column("questions", "created_by"):
        op.add_column("questions", sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True))
    if not _has_index("questions", "ix_questions_created_by"):
        op.create_index("ix_questions_created_by", "questions", ["created_by"])
    if not _has_index("papers", "ix_papers_user_id"):
        op.create_index("ix_papers_user_id", "papers", ["user_id"])
    if not _has_index("practice_sessions", "ix_practice_sessions_user_id"):
        op.create_index("ix_practice_sessions_user_id", "practice_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_practice_sessions_user_id", table_name="practice_sessions")
    op.drop_index("ix_papers_user_id", table_name="papers")
    op.drop_index("ix_questions_created_by", table_name="questions")
    op.drop_column("questions", "created_by")
