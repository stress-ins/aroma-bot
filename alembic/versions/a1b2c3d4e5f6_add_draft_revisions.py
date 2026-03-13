"""Add draft_revisions table

Revision ID: a1b2c3d4e5f6
Revises: 4d6b8e9f1a2c
Create Date: 2026-03-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "4d6b8e9f1a2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "draft_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.String(length=32), nullable=False),
        sa.Column("rev_num", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("author", sa.String(length=64), nullable=False, server_default="user"),
        sa.Column("note", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_draft_revisions_draft_id_rev_num",
        "draft_revisions",
        ["draft_id", "rev_num"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_draft_revisions_draft_id_rev_num", table_name="draft_revisions")
    op.drop_table("draft_revisions")
