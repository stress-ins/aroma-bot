"""add video_tasks table

Revision ID: 3480a99eb0c3
Revises: 89af2dab715b
Create Date: 2026-03-24 18:40:20.574857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3480a99eb0c3'
down_revision: Union[str, Sequence[str], None] = '89af2dab715b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create video_tasks table for persistent video processing queue."""
    op.create_table('video_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('draft_id', sa.String(length=32), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=True),
        sa.Column('task_type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('step', sa.String(length=40), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('video_duration', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_video_tasks_task_id', 'video_tasks', ['task_id'], unique=True)
    op.create_index('ix_video_tasks_draft_id', 'video_tasks', ['draft_id'], unique=False)
    op.create_index('ix_video_tasks_status', 'video_tasks', ['status'], unique=False)


def downgrade() -> None:
    """Drop video_tasks table."""
    op.drop_index('ix_video_tasks_status', table_name='video_tasks')
    op.drop_index('ix_video_tasks_draft_id', table_name='video_tasks')
    op.drop_index('ix_video_tasks_task_id', table_name='video_tasks')
    op.drop_table('video_tasks')
