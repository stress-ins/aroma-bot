"""add daily oil context and city settings

Revision ID: 989b1621a261
Revises: e89683dd7597
Create Date: 2026-03-18 11:16:57.427857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '989b1621a261'
down_revision: Union[str, Sequence[str], None] = 'e89683dd7597'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add reason+context to daily_oils, city fields to brand_settings."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # daily_oils: add reason and context columns
    daily_cols = [c["name"] for c in inspector.get_columns("daily_oils")]
    with op.batch_alter_table("daily_oils") as batch_op:
        if "reason" not in daily_cols:
            batch_op.add_column(
                sa.Column("reason", sa.String(500), server_default="", nullable=False)
            )
        if "context" not in daily_cols:
            batch_op.add_column(
                sa.Column("context", sa.JSON(), server_default="{}", nullable=True)
            )

    # brand_settings: add city fields
    brand_cols = [c["name"] for c in inspector.get_columns("brand_settings")]
    with op.batch_alter_table("brand_settings") as batch_op:
        if "city_name" not in brand_cols:
            batch_op.add_column(
                sa.Column("city_name", sa.String(100), server_default="Москва", nullable=False)
            )
        if "city_lat" not in brand_cols:
            batch_op.add_column(
                sa.Column("city_lat", sa.Float(), server_default="55.7558", nullable=False)
            )
        if "city_lon" not in brand_cols:
            batch_op.add_column(
                sa.Column("city_lon", sa.Float(), server_default="37.6173", nullable=False)
            )


def downgrade() -> None:
    """Remove added columns."""
    with op.batch_alter_table("brand_settings") as batch_op:
        batch_op.drop_column("city_lon")
        batch_op.drop_column("city_lat")
        batch_op.drop_column("city_name")
    with op.batch_alter_table("daily_oils") as batch_op:
        batch_op.drop_column("context")
        batch_op.drop_column("reason")
