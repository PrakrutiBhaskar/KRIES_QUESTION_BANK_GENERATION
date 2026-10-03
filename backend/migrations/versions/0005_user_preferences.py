"""Per-user preferences.

Adds the nullable `users.preferences` JSON column that backs the Settings page
(theme, notifications, generation defaults). Existing users keep NULL and get the
defaults until they save something.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
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
    if _has_column("users", "preferences"):
        return
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences")
