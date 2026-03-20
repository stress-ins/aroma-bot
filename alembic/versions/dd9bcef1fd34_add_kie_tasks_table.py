"""add_kie_tasks_table

Revision ID: dd9bcef1fd34
Revises: e151b4f49743
Create Date: 2026-03-20 15:07:35.394132

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'dd9bcef1fd34'
down_revision: Union[str, Sequence[str], None] = 'e151b4f49743'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('kie_tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('draft_id', sa.String(length=32), nullable=True),
    sa.Column('content_type', sa.String(length=32), nullable=False),
    sa.Column('slot_key', sa.String(length=64), nullable=False),
    sa.Column('prompt', sa.String(length=4000), nullable=False),
    sa.Column('aspect_ratio', sa.String(length=8), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('image_url', sa.String(length=1024), nullable=False),
    sa.Column('error_message', sa.String(length=1000), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_kie_tasks_draft_id'), 'kie_tasks', ['draft_id'], unique=False)
    op.create_index(op.f('ix_kie_tasks_status'), 'kie_tasks', ['status'], unique=False)
    op.create_index(op.f('ix_kie_tasks_task_id'), 'kie_tasks', ['task_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_kie_tasks_task_id'), table_name='kie_tasks')
    op.drop_index(op.f('ix_kie_tasks_status'), table_name='kie_tasks')
    op.drop_index(op.f('ix_kie_tasks_draft_id'), table_name='kie_tasks')
    op.drop_table('kie_tasks')
