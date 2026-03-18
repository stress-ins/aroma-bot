"""rename Default/Personal teams to Персональная

Revision ID: a1b2c3d4e5f7
Revises: fddf1b716f38
Create Date: 2026-03-18 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = 'fddf1b716f38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE teams SET name = 'Персональная', slug = 'персональная' WHERE name IN ('Default', 'Personal') AND slug IN ('default', 'personal')")


def downgrade() -> None:
    pass
