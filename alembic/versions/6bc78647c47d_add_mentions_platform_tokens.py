"""add mentions platform tokens

Revision ID: 6bc78647c47d
Revises: 67bb541f5dab
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '6bc78647c47d'
down_revision: Union[str, Sequence[str], None] = '67bb541f5dab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables created on VPS — stub for local alignment
    pass


def downgrade() -> None:
    pass
