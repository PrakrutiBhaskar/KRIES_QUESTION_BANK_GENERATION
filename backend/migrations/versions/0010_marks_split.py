"""Teacher-editable marks split on questions.

Adds one nullable column, `questions.marks_split` (JSON): the split of a
question's marks across answer-key components, e.g.
[{"name": "Diagram", "marks": 2}, {"name": "Explanation", "marks": 3}].
NULL keeps the automatic split, so existing questions are unchanged.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None
# The app's startup schema sync may already have added the column, so check first.


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return insp.has_table(table) and column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("questions", "marks_split"):
        op.add_column("questions", sa.Column("marks_split", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("marks_split")
