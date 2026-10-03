"""Figure metadata for figure-based question generation.

Adds four nullable columns to `figures`:

  * subject / chapter  - where the figure belongs (library lookup on generate)
  * topic              - optional sub-topic
  * labels             - the labelled parts, e.g. ["A: nucleus", "B: cell wall"]

The generator works from the caption plus these, never from the image itself.
All nullable, so existing figures keep working and simply have no metadata.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
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
    bind = op.get_bind()
    labels_type = (
        postgresql.ARRAY(sa.Text()) if bind.dialect.name == "postgresql" else sa.JSON()
    )
    for name, col_type in (
        ("subject", sa.Text()),
        ("chapter", sa.Text()),
        ("topic", sa.Text()),
        ("labels", labels_type),
    ):
        if not _has_column("figures", name):
            op.add_column("figures", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("figures") as batch:
        batch.drop_column("labels")
        batch.drop_column("topic")
        batch.drop_column("chapter")
        batch.drop_column("subject")
