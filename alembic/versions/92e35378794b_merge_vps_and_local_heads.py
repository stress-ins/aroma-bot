"""merge vps and local heads

Revision ID: 92e35378794b
Revises: 6bc78647c47d, b2efc9c405f9
Create Date: 2026-03-15 23:37:10.230228

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92e35378794b'
down_revision: Union[str, Sequence[str], None] = ('6bc78647c47d', 'b2efc9c405f9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
