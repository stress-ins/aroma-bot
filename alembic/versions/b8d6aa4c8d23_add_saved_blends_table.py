"""add saved_blends table

Revision ID: b8d6aa4c8d23
Revises: 7f66b3397da4
Create Date: 2026-03-17 00:14:44.050230

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d6aa4c8d23'
down_revision: Union[str, Sequence[str], None] = '7f66b3397da4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "saved_blends",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("saved_id", sa.String(36), unique=True, index=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger, index=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("brief", sa.String(1000), server_default=""),
        sa.Column("tags", sa.JSON, server_default="[]"),
        sa.Column("oils", sa.JSON, server_default="[]"),
        sa.Column("total_drops", sa.Integer, server_default="0"),
        sa.Column("profile", sa.JSON, server_default="{}"),
        sa.Column("expert_note", sa.String(2000), server_default=""),
        sa.Column("application_guide", sa.String(1000), server_default=""),
        sa.Column("safety_status", sa.String(16), server_default="safe"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
        if_not_exists=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("saved_blends")
