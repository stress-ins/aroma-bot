"""Add reference category to aroma cards

Revision ID: c3b91e2d7a44
Revises: 8f2a1c9d4e11
Create Date: 2026-03-12 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3b91e2d7a44"
down_revision: Union[str, Sequence[str], None] = "8f2a1c9d4e11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite doesn't support ALTER COLUMN SET NOT NULL well. 
    # Adding with a server_default is safer.
    op.add_column("aroma_cards", sa.Column("category", sa.String(length=32), nullable=False, server_default="aroma"))
    op.create_index(op.f("ix_aroma_cards_category"), "aroma_cards", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_aroma_cards_category"), table_name="aroma_cards")
    op.drop_column("aroma_cards", "category")
