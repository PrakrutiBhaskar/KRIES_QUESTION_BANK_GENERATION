"""Figures: diagrams attached to questions and answer keys.

Creates the `figures` table (image metadata; the files live in FIGURE_DIR) and
adds two nullable columns to `questions`:

  * figure_id         - printed with the question in the paper
  * answer_figure_id  - printed only in the answer key

Both reference figures.id with ON DELETE SET NULL. Existing questions keep NULL
in both columns and render exactly as before. Batch mode is used for the
`questions` changes so the same migration works on SQLite, which cannot add or
drop a foreign-key column in place.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
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
    if not sa.inspect(op.get_bind()).has_table("figures"):
        _create_figures_table()

    with op.batch_alter_table("questions") as batch:
        for col in ("figure_id", "answer_figure_id"):
            if not _has_column("questions", col):
                batch.add_column(sa.Column(col, sa.Uuid(as_uuid=True), nullable=True))
        for name, col in (
            ("fk_questions_figure_id", "figure_id"),
            ("fk_questions_answer_figure_id", "answer_figure_id"),
        ):
            if not _has_fk("questions", name):
                batch.create_foreign_key(name, "figures", [col], ["id"], ondelete="SET NULL")
        for name, col in (
            ("ix_questions_figure_id", "figure_id"),
            ("ix_questions_answer_figure_id", "answer_figure_id"),
        ):
            if not _has_index("questions", name):
                batch.create_index(name, [col])


def _create_figures_table() -> None:
    op.create_table(
        "figures",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("filename", name="uq_figures_filename"),
    )
    op.create_index("ix_figures_owner_id", "figures", ["owner_id"])


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.drop_index("ix_questions_answer_figure_id")
        batch.drop_index("ix_questions_figure_id")
        batch.drop_constraint("fk_questions_answer_figure_id", type_="foreignkey")
        batch.drop_constraint("fk_questions_figure_id", type_="foreignkey")
        batch.drop_column("answer_figure_id")
        batch.drop_column("figure_id")
    op.drop_index("ix_figures_owner_id", table_name="figures")
    op.drop_table("figures")
