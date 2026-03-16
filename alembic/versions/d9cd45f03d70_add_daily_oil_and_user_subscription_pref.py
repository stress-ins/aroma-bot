"""add daily_oil and user subscription pref

Revision ID: d9cd45f03d70
Revises: 87c4fd490012
Create Date: 2026-03-17 01:34:20.029046

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9cd45f03d70'
down_revision: Union[str, Sequence[str], None] = 'b8d6aa4c8d23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # Create daily_oils table if it doesn't exist
    inspector = sa.inspect(conn)
    if "daily_oils" not in inspector.get_table_names():
        op.create_table(
            'daily_oils',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('date', sa.String(16), nullable=False),
            sa.Column('slug', sa.String(64), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('fact', sa.String(1000), server_default=''),
            sa.Column('daily_practice', sa.String(1000), server_default=''),
            sa.Column('sent_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_daily_oils_date', 'daily_oils', ['date'], unique=True)

    # Add daily_oil_subscribed to user_profiles if missing
    columns = [c["name"] for c in inspector.get_columns("user_profiles")]
    if "daily_oil_subscribed" not in columns:
        with op.batch_alter_table('user_profiles') as batch_op:
            batch_op.add_column(
                sa.Column('daily_oil_subscribed', sa.Boolean(), server_default='1', nullable=False)
            )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user_profiles') as batch_op:
        batch_op.drop_column('daily_oil_subscribed')
    op.drop_index('ix_daily_oils_date', table_name='daily_oils')
    op.drop_table('daily_oils')
