"""Add aroma cards

Revision ID: 8f2a1c9d4e11
Revises: 61470564f6cb
Create Date: 2026-03-11 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f2a1c9d4e11"
down_revision: Union[str, Sequence[str], None] = "61470564f6cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "aroma_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_aroma_cards_name"), "aroma_cards", ["name"], unique=False)
    op.create_index(op.f("ix_aroma_cards_slug"), "aroma_cards", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_aroma_cards_slug"), table_name="aroma_cards")
    op.drop_index(op.f("ix_aroma_cards_name"), table_name="aroma_cards")
    op.drop_table("aroma_cards")
