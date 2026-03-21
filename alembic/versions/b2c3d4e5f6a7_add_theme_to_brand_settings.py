"""add theme to brand_settings

Revision ID: b2c3d4e5f6a7
Revises: dd9bcef1fd34
Create Date: 2026-03-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'dd9bcef1fd34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('brand_settings',
        sa.Column('theme', sa.String(32), nullable=False, server_default='terracotta'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('brand_settings', 'theme')
