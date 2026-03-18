"""add updated_at to drafts

Revision ID: 9fe8ad9cf988
Revises: a1b2c3d4e5f7
Create Date: 2026-03-18 21:33:17.889247

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '9fe8ad9cf988'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('drafts', sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('drafts', 'updated_at')
