"""Chapters seeded from the Syllabus page.

Adds the `seeded_chapters` table: chapters (with optional topics) that teachers
and administrators add to a subject's grade syllabus from the app. New table
only, so existing data is untouched.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None
# The app's startup schema sync (create_all) may already have made the table.


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("seeded_chapters"):
        return
    op.create_table(
        "seeded_chapters",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("subject", "grade", "name_key", name="uq_seeded_chapters"),
        sa.CheckConstraint("grade IN (7, 8, 9)", name="ck_seeded_chapters_grade"),
    )
    op.create_index("ix_seeded_chapters_created_by", "seeded_chapters", ["created_by"])


def downgrade() -> None:
    op.drop_table("seeded_chapters")
