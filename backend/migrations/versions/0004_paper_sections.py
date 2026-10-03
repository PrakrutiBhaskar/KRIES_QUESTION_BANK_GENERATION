"""Sections on paper questions, for blueprint-based papers.

Adds the nullable `paper_questions.section` column. Existing papers keep a NULL
section and render as one flat list, as before.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
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
    if not _has_column("paper_questions", "section"):
        op.add_column("paper_questions", sa.Column("section", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("paper_questions", "section")
