"""add social trends tables

Revision ID: a2b3c4d5e6f7
Revises: 9fe8ad9cf988
Create Date: 2026-03-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = '9fe8ad9cf988'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    )
    return result.scalar() is not None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def _safe_add_column(table: str, column: sa.Column) -> None:
    if _table_exists(table) and not _column_exists(table, column.name):
        op.add_column(table, column)


def upgrade() -> None:
    """Create social_trend_posts, hashtag_quotas tables; extend brand_settings."""
    if not _table_exists('social_trend_posts'):
        op.create_table(
            'social_trend_posts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('team_id', sa.String(length=36), nullable=True),
            sa.Column('platform', sa.String(length=16), nullable=False),
            sa.Column('source_type', sa.String(length=16), nullable=False),
            sa.Column('source_value', sa.String(length=128), nullable=False),
            sa.Column('post_id', sa.String(length=128), nullable=False),
            sa.Column('author_username', sa.String(length=255), nullable=False),
            sa.Column('text', sa.String(), nullable=False),
            sa.Column('permalink', sa.String(length=512), nullable=False),
            sa.Column('media_type', sa.String(length=32), nullable=False),
            sa.Column('thumbnail_url', sa.String(), nullable=False),
            sa.Column('hashtags', sa.JSON(), nullable=True),
            sa.Column('like_count', sa.Integer(), nullable=False),
            sa.Column('comment_count', sa.Integer(), nullable=False),
            sa.Column('share_count', sa.Integer(), nullable=False),
            sa.Column('reply_count', sa.Integer(), nullable=False),
            sa.Column('view_count', sa.Integer(), nullable=False),
            sa.Column('posted_at', sa.DateTime(), nullable=True),
            sa.Column('collected_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['team_id'], ['teams.team_id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_social_trend_posts_team_id'), 'social_trend_posts', ['team_id'])
        op.create_index(op.f('ix_social_trend_posts_platform'), 'social_trend_posts', ['platform'])
        op.create_index(op.f('ix_social_trend_posts_post_id'), 'social_trend_posts', ['post_id'], unique=True)
        op.create_index(op.f('ix_social_trend_posts_posted_at'), 'social_trend_posts', ['posted_at'])

    if not _table_exists('hashtag_quotas'):
        op.create_table(
            'hashtag_quotas',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('team_id', sa.String(length=36), nullable=True),
            sa.Column('hashtag', sa.String(length=128), nullable=False),
            sa.Column('searched_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['team_id'], ['teams.team_id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_hashtag_quotas_team_id'), 'hashtag_quotas', ['team_id'])

    # Extend brand_settings with monitored accounts
    _safe_add_column('brand_settings', sa.Column('instagram_accounts', sa.JSON(), server_default='[]'))
    _safe_add_column('brand_settings', sa.Column('threads_accounts', sa.JSON(), server_default='[]'))


def downgrade() -> None:
    """Remove social trends tables and columns."""
    if _table_exists('brand_settings'):
        if _column_exists('brand_settings', 'threads_accounts'):
            op.drop_column('brand_settings', 'threads_accounts')
        if _column_exists('brand_settings', 'instagram_accounts'):
            op.drop_column('brand_settings', 'instagram_accounts')

    if _table_exists('hashtag_quotas'):
        op.drop_index(op.f('ix_hashtag_quotas_team_id'), table_name='hashtag_quotas')
        op.drop_table('hashtag_quotas')

    if _table_exists('social_trend_posts'):
        op.drop_index(op.f('ix_social_trend_posts_posted_at'), table_name='social_trend_posts')
        op.drop_index(op.f('ix_social_trend_posts_post_id'), table_name='social_trend_posts')
        op.drop_index(op.f('ix_social_trend_posts_platform'), table_name='social_trend_posts')
        op.drop_index(op.f('ix_social_trend_posts_team_id'), table_name='social_trend_posts')
        op.drop_table('social_trend_posts')
