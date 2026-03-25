"""Add city fields to teams table (per-team city override).

Revision ID: a7b8c9d0e1f2
Revises: 3480a99eb0c3
Create Date: 2026-03-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = '3480a99eb0c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('teams', sa.Column('city_name', sa.String(100), nullable=True))
    op.add_column('teams', sa.Column('city_lat', sa.Float, nullable=True))
    op.add_column('teams', sa.Column('city_lon', sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column('teams', 'city_lon')
    op.drop_column('teams', 'city_lat')
    op.drop_column('teams', 'city_name')
