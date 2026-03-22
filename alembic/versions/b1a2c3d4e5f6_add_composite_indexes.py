"""add_composite_indexes

Revision ID: b1a2c3d4e5f6
Revises: 97734efba4e5
Create Date: 2026-03-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "c3b91e2d7a44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite indexes for frequent queries
    for name, table, columns in [
        ("ix_draft_team_created", "drafts", ["team_id", "created_at"]),
        ("ix_draft_team_status", "drafts", ["team_id", "status"]),
        ("ix_plan_team_created", "plans", ["team_id", "created_at"]),
        ("ix_publish_log_draft_created", "publish_log", ["draft_id", "created_at"]),
    ]:
        try:
            op.create_index(name, table, columns)
        except Exception:
            pass  # index may already exist


def downgrade() -> None:
    for name, table in [
        ("ix_publish_log_draft_created", "publish_log"),
        ("ix_plan_team_created", "plans"),
        ("ix_draft_team_status", "drafts"),
        ("ix_draft_team_created", "drafts"),
    ]:
        try:
            op.drop_index(name, table_name=table)
        except Exception:
            pass
