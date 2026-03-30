"""add profile_picture_url to conversations

Revision ID: a1b2c3d4e5f6
Revises: 2decb05ae2b6
Create Date: 2026-03-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "2decb05ae2b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("profile_picture_url", sa.String(1024), server_default="", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_column("profile_picture_url")
