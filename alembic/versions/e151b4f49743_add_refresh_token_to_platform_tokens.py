"""add refresh_token to platform_tokens

Revision ID: e151b4f49743
Revises: 59d3a878f513
Create Date: 2026-03-19 20:11:17.096374

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e151b4f49743'
down_revision: Union[str, Sequence[str], None] = '59d3a878f513'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('platform_tokens', sa.Column('refresh_token', sa.String(length=1024), server_default='', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('platform_tokens', 'refresh_token')
