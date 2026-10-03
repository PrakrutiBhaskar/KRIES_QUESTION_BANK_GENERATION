"""Answer-key verification result on each question.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
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
    # Nullable: existing questions were never checked and read as "unverified".
    for name in ("verification_status", "verification_note"):
        if not _has_column("questions", name):
            op.add_column("questions", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "verification_note")
    op.drop_column("questions", "verification_status")
