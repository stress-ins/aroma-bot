"""add digest_cache table

Revision ID: f1c724919ed8
Revises: c4d5e6f7a8b9
Create Date: 2026-03-28 20:56:29.806189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1c724919ed8'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('digest_cache',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cache_key', sa.String(length=64), nullable=False),
    sa.Column('value_json', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_digest_cache_cache_key'), 'digest_cache', ['cache_key'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_digest_cache_cache_key'), table_name='digest_cache')
    op.drop_table('digest_cache')
