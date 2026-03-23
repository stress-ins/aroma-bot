"""add first_name to team_members

Revision ID: 89af2dab715b
Revises: c3cdd275c2a1
Create Date: 2026-03-23 09:02:50.597640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '89af2dab715b'
down_revision: Union[str, Sequence[str], None] = 'c3cdd275c2a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("team_members") as batch_op:
        batch_op.add_column(sa.Column("first_name", sa.String(128), server_default="", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("team_members") as batch_op:
        batch_op.drop_column("first_name")
