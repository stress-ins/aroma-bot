"""add team workspace tables and FK extensions

Revision ID: 4d0dc14a42b8
Revises: 989b1621a261
Create Date: 2026-03-18 12:07:30.045221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4d0dc14a42b8'
down_revision: Union[str, Sequence[str], None] = '989b1621a261'
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


def _safe_create_index(index_name, table: str, columns, **kw) -> None:
    if _table_exists(table):
        try:
            op.create_index(index_name, table, columns, **kw)
        except Exception:
            pass  # Index may already exist


def upgrade() -> None:
    """Upgrade schema."""
    # --- New tables ---
    op.create_table('teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_teams_slug'), 'teams', ['slug'], unique=True)
    op.create_index(op.f('ix_teams_team_id'), 'teams', ['team_id'], unique=True)

    op.create_table('team_invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invite_code', sa.String(length=32), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=False),
        sa.Column('uses_count', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.team_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_team_invites_invite_code'), 'team_invites', ['invite_code'], unique=True)
    op.create_index(op.f('ix_team_invites_team_id'), 'team_invites', ['team_id'], unique=False)

    op.create_table('team_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.team_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'telegram_id'),
    )
    op.create_index(op.f('ix_team_members_team_id'), 'team_members', ['team_id'], unique=False)
    op.create_index(op.f('ix_team_members_telegram_id'), 'team_members', ['telegram_id'], unique=False)

    # --- Add nullable team_id columns to existing tables ---
    # Some tables (mentions, platform_tokens, post_metrics) may not exist in fresh DBs
    # because their migrations are stubs — they were created on VPS via init_db().
    # Use defensive helpers to handle both cases.
    _safe_add_column('drafts', sa.Column('team_id', sa.String(length=36), nullable=True))
    _safe_add_column('drafts', sa.Column('created_by', sa.BigInteger(), nullable=True))
    _safe_create_index(op.f('ix_drafts_team_id'), 'drafts', ['team_id'], unique=False)

    _safe_add_column('plans', sa.Column('team_id', sa.String(length=36), nullable=True))
    _safe_create_index(op.f('ix_plans_team_id'), 'plans', ['team_id'], unique=False)

    _safe_add_column('publish_log', sa.Column('team_id', sa.String(length=36), nullable=True))
    _safe_create_index(op.f('ix_publish_log_team_id'), 'publish_log', ['team_id'], unique=False)

    _safe_add_column('brand_settings', sa.Column('team_id', sa.String(length=36), nullable=True))

    _safe_add_column('draft_revisions', sa.Column('author_telegram_id', sa.BigInteger(), nullable=True))

    _safe_add_column('mentions', sa.Column('team_id', sa.String(length=36), nullable=True))
    _safe_create_index(op.f('ix_mentions_team_id'), 'mentions', ['team_id'], unique=False)

    _safe_add_column('saved_blends', sa.Column('team_id', sa.String(length=36), nullable=True))
    _safe_create_index(op.f('ix_saved_blends_team_id'), 'saved_blends', ['team_id'], unique=False)

    _safe_add_column('platform_tokens', sa.Column('team_id', sa.String(length=36), nullable=True))
    _safe_create_index(op.f('ix_platform_tokens_team_id'), 'platform_tokens', ['team_id'], unique=False)

    _safe_add_column('post_metrics', sa.Column('team_id', sa.String(length=36), nullable=True))
    _safe_create_index(op.f('ix_post_metrics_team_id'), 'post_metrics', ['team_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    for table, col in [
        ('post_metrics', 'team_id'),
        ('platform_tokens', 'team_id'),
        ('saved_blends', 'team_id'),
        ('mentions', 'team_id'),
        ('draft_revisions', 'author_telegram_id'),
        ('brand_settings', 'team_id'),
        ('publish_log', 'team_id'),
        ('plans', 'team_id'),
        ('drafts', 'created_by'),
        ('drafts', 'team_id'),
    ]:
        if _table_exists(table) and _column_exists(table, col):
            idx_name = f'ix_{table}_{col}'
            try:
                op.drop_index(op.f(idx_name), table_name=table)
            except Exception:
                pass
            op.drop_column(table, col)

    op.drop_index(op.f('ix_team_members_telegram_id'), table_name='team_members')
    op.drop_index(op.f('ix_team_members_team_id'), table_name='team_members')
    op.drop_table('team_members')
    op.drop_index(op.f('ix_team_invites_team_id'), table_name='team_invites')
    op.drop_index(op.f('ix_team_invites_invite_code'), table_name='team_invites')
    op.drop_table('team_invites')
    op.drop_index(op.f('ix_teams_team_id'), table_name='teams')
    op.drop_index(op.f('ix_teams_slug'), table_name='teams')
    op.drop_table('teams')
