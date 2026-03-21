"""add past_publications table and content_pillars

Revision ID: a3331ac4446f
Revises: b2c3d4e5f6a7
Create Date: 2026-03-21 22:30:55.917557

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3331ac4446f'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('past_publications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pub_id', sa.String(length=36), nullable=False),
    sa.Column('team_id', sa.String(length=36), nullable=True),
    sa.Column('created_by', sa.BigInteger(), nullable=True),
    sa.Column('draft_id', sa.String(length=32), nullable=True),
    sa.Column('platform', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('external_url', sa.String(length=1024), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=False),
    sa.Column('topic', sa.String(length=255), nullable=False),
    sa.Column('caption', sa.String(length=4000), nullable=False),
    sa.Column('hashtags', sa.JSON(), nullable=False),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('likes', sa.Integer(), nullable=False),
    sa.Column('comments', sa.Integer(), nullable=False),
    sa.Column('shares', sa.Integer(), nullable=False),
    sa.Column('saves', sa.Integer(), nullable=False),
    sa.Column('views', sa.Integer(), nullable=False),
    sa.Column('score_engagement', sa.Integer(), nullable=True),
    sa.Column('score_brand_fit', sa.Integer(), nullable=True),
    sa.Column('score_craft', sa.Integer(), nullable=True),
    sa.Column('score_goal_hit', sa.Integer(), nullable=True),
    sa.Column('content_pillar', sa.String(length=64), nullable=False),
    sa.Column('funnel_stage', sa.String(length=32), nullable=False),
    sa.Column('notes', sa.String(length=1000), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['teams.team_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_past_publications_draft_id'), 'past_publications', ['draft_id'], unique=False)
    op.create_index(op.f('ix_past_publications_platform'), 'past_publications', ['platform'], unique=False)
    op.create_index(op.f('ix_past_publications_pub_id'), 'past_publications', ['pub_id'], unique=True)
    op.create_index(op.f('ix_past_publications_published_at'), 'past_publications', ['published_at'], unique=False)
    op.create_index(op.f('ix_past_publications_team_id'), 'past_publications', ['team_id'], unique=False)
    op.add_column('brand_settings', sa.Column('content_pillars', sa.JSON(), nullable=True, server_default='[]'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('brand_settings', 'content_pillars')
    op.drop_index(op.f('ix_past_publications_team_id'), table_name='past_publications')
    op.drop_index(op.f('ix_past_publications_published_at'), table_name='past_publications')
    op.drop_index(op.f('ix_past_publications_pub_id'), table_name='past_publications')
    op.drop_index(op.f('ix_past_publications_platform'), table_name='past_publications')
    op.drop_index(op.f('ix_past_publications_draft_id'), table_name='past_publications')
    op.drop_table('past_publications')
