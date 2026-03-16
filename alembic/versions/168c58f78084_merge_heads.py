"""merge heads

Revision ID: 168c58f78084
Revises: 78af5cd44ddf, f78119590d91
Create Date: 2026-03-17 00:09:37.189329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '168c58f78084'
down_revision: Union[str, Sequence[str], None] = ('78af5cd44ddf', 'f78119590d91')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
