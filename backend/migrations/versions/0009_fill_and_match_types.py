"""Fill-in-the-blank and match-the-following question types.

Adds two values, "Fill" and "Match", to the PostgreSQL `question_type` enum
(MCQ, Short, Long). Nothing else changes: a Match question keeps Column A in
`text`, Column B in the existing `options` column and its key in `answer`.

PostgreSQL only. Elsewhere (SQLite in the tests) the column is a plain string,
so there is nothing to do. The app's startup schema sync may already have added
the values, so `IF NOT EXISTS` makes this safe to run either way.

`ADD VALUE` cannot run inside a transaction block on PostgreSQL older than 12,
so it runs in an autocommit block.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-03
"""
from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

NEW_VALUES = ("Fill", "Match")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for value in NEW_VALUES:
            op.execute(f"ALTER TYPE question_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum, and rewriting the column to
    # do it would fail as soon as a Fill or Match question exists. The extra
    # values are harmless to older code, so a downgrade leaves them in place.
    pass
