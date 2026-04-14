"""add regens_used to usage_logs

Revision ID: af70d29621d0
Revises: 012e86cc75c5
Create Date: 2026-04-14 20:24:20.399045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'af70d29621d0'
down_revision: Union[str, Sequence[str], None] = '012e86cc75c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add regens_used column to usage_logs for monthly regen tracking."""
    op.add_column('usage_logs', sa.Column('regens_used', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Remove regens_used column."""
    op.drop_column('usage_logs', 'regens_used')
