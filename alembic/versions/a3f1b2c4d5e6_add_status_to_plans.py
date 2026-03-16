"""add status to plans

Revision ID: a3f1b2c4d5e6
Revises: d9cd45f03d70
Create Date: 2026-03-17 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a3f1b2c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd9cd45f03d70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plans', sa.Column('status', sa.String(length=32), server_default='draft', nullable=False))


def downgrade() -> None:
    op.drop_column('plans', 'status')
