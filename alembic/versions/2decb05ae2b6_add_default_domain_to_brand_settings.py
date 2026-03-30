"""add default_domain to brand_settings

Revision ID: 2decb05ae2b6
Revises: ce52aca42080
Create Date: 2026-03-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2decb05ae2b6'
down_revision: Union[str, Sequence[str], None] = 'ce52aca42080'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add default_domain column to brand_settings table."""
    with op.batch_alter_table("brand_settings") as batch_op:
        batch_op.add_column(sa.Column("default_domain", sa.String(20), server_default="aroma", nullable=False))


def downgrade() -> None:
    """Remove default_domain column from brand_settings table."""
    with op.batch_alter_table("brand_settings") as batch_op:
        batch_op.drop_column("default_domain")
