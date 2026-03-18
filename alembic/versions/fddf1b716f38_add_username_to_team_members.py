"""add username to team_members

Revision ID: fddf1b716f38
Revises: ff3d944b8233
Create Date: 2026-03-18 14:52:51.763424

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fddf1b716f38'
down_revision: Union[str, Sequence[str], None] = 'ff3d944b8233'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('team_members', sa.Column('username', sa.String(length=128), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('team_members', 'username')
