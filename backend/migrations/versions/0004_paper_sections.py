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


def upgrade() -> None:
    op.add_column("paper_questions", sa.Column("section", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("paper_questions", "section")
