"""Add plans table

Revision ID: 4d6b8e9f1a2c
Revises: c3b91e2d7a44
Create Date: 2026-03-12 18:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d6b8e9f1a2c"
down_revision: Union[str, Sequence[str], None] = "c3b91e2d7a44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.String(length=32), nullable=False),
        sa.Column("raw_text", sa.String(), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plans_plan_id"), "plans", ["plan_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_plans_plan_id"), table_name="plans")
    op.drop_table("plans")
