"""add tracked_hashtags to brand_settings

Revision ID: 59d3a878f513
Revises: a2b3c4d5e6f7
Create Date: 2026-03-19 12:44:07.734481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '59d3a878f513'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('brand_settings', sa.Column('tracked_hashtags', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('brand_settings', 'tracked_hashtags')
