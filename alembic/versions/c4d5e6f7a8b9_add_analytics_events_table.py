"""add analytics_events table

Revision ID: c4d5e6f7a8b9
Revises: a7b8c9d0e1f2
Create Date: 2026-03-25 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'analytics_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=True),
        sa.Column('telegram_id', sa.BigInteger(), nullable=True),
        sa.Column('event_name', sa.String(length=64), nullable=False),
        sa.Column('event_category', sa.String(length=32), nullable=False),
        sa.Column('event_data', sa.JSON(), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.team_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_analytics_events_team_id', 'analytics_events', ['team_id'])
    op.create_index('ix_analytics_events_event_name', 'analytics_events', ['event_name'])
    op.create_index('ix_analytics_events_session_id', 'analytics_events', ['session_id'])
    op.create_index('ix_analytics_events_created_at', 'analytics_events', ['created_at'])
    op.create_index(
        'ix_analytics_team_event_created',
        'analytics_events',
        ['team_id', 'event_name', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_analytics_team_event_created', table_name='analytics_events')
    op.drop_index('ix_analytics_events_created_at', table_name='analytics_events')
    op.drop_index('ix_analytics_events_session_id', table_name='analytics_events')
    op.drop_index('ix_analytics_events_event_name', table_name='analytics_events')
    op.drop_index('ix_analytics_events_team_id', table_name='analytics_events')
    op.drop_table('analytics_events')
