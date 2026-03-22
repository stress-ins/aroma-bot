"""merge migration heads

Revision ID: c3cdd275c2a1
Revises: 97734efba4e5, b1a2c3d4e5f6
Create Date: 2026-03-22 21:25:05.102279

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3cdd275c2a1'
down_revision: Union[str, Sequence[str], None] = ('97734efba4e5', 'b1a2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
