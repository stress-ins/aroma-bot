"""merge heads: digest_cache + previous

Revision ID: ce52aca42080
Revises: d1e2f3a4b5c6, f1c724919ed8
Create Date: 2026-03-28 22:02:20.240795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce52aca42080'
down_revision: Union[str, Sequence[str], None] = ('d1e2f3a4b5c6', 'f1c724919ed8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
