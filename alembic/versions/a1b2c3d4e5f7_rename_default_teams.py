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
    # Rename each matching team individually with a unique slug (append created_by)
    # to avoid UNIQUE constraint on the globally-unique slug index.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, created_by FROM teams WHERE slug IN ('default', 'personal')")
    ).fetchall()
    for row_id, created_by in rows:
        slug = f"персональная-{created_by}"
        conn.execute(
            sa.text("UPDATE teams SET name = :name, slug = :slug WHERE id = :id"),
            {"name": "Персональная", "slug": slug, "id": row_id},
        )


def downgrade() -> None:
    pass
