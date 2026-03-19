"""add post_metrics table

Revision ID: 7f66b3397da4
Revises: f78119590d91
Create Date: 2026-03-17 00:09:45.154479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f66b3397da4'
down_revision: Union[str, Sequence[str], None] = 'f78119590d91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'post_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('draft_id', sa.String(32), nullable=False, index=True),
        sa.Column('team_id', sa.String(36), sa.ForeignKey('teams.team_id'), nullable=True, index=True),
        sa.Column('platform', sa.String(32), nullable=False),
        sa.Column('external_id', sa.String(255), server_default=''),
        sa.Column('metrics', sa.JSON(), server_default='{}'),
        sa.Column('fetched_at', sa.DateTime()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('post_metrics')
