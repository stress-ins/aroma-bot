"""merge daily_oil and tracked_threads heads

Revision ID: b1c2d3e4f5a6
Revises: a3f1b2c4d5e6, af4842639fd7
Create Date: 2026-03-17 12:00:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = ('a3f1b2c4d5e6', 'af4842639fd7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
