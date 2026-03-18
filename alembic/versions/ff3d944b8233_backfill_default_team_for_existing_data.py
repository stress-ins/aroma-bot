"""backfill default team for existing data

Revision ID: ff3d944b8233
Revises: 4d0dc14a42b8
Create Date: 2026-03-18 12:36:33.353031

"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision: str = 'ff3d944b8233'
down_revision: Union[str, Sequence[str], None] = '4d0dc14a42b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_TEAM_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_TEAM_SLUG = "default"


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    )
    return result.scalar() is not None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    """Backfill: create default team + assign existing data to it."""
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    # Check if default team already exists
    existing = conn.execute(
        sa.text("SELECT team_id FROM teams WHERE team_id = :tid"),
        {"tid": DEFAULT_TEAM_ID},
    ).scalar()

    if not existing:
        # Try to find admin user from user_profiles (first user = admin)
        admin_id = 0
        if _table_exists("user_profiles"):
            admin_id = conn.execute(
                sa.text("SELECT telegram_id FROM user_profiles ORDER BY created_at ASC LIMIT 1")
            ).scalar() or 0

        conn.execute(
            sa.text(
                "INSERT INTO teams (team_id, name, slug, created_by, created_at, updated_at) "
                "VALUES (:tid, :name, :slug, :admin, :now, :now)"
            ),
            {"tid": DEFAULT_TEAM_ID, "name": "Default", "slug": DEFAULT_TEAM_SLUG, "admin": admin_id, "now": now},
        )

        # Add admin as owner if they exist
        if admin_id:
            conn.execute(
                sa.text(
                    "INSERT OR IGNORE INTO team_members (team_id, telegram_id, role, joined_at) "
                    "VALUES (:tid, :uid, 'owner', :now)"
                ),
                {"tid": DEFAULT_TEAM_ID, "uid": admin_id, "now": now},
            )

    # Backfill team_id on all tables that have the column
    tables_with_team_id = [
        "drafts", "plans", "publish_log", "brand_settings",
        "mentions", "saved_blends", "platform_tokens", "post_metrics",
    ]
    for table in tables_with_team_id:
        if _table_exists(table) and _column_exists(table, "team_id"):
            conn.execute(
                sa.text(f"UPDATE {table} SET team_id = :tid WHERE team_id IS NULL"),
                {"tid": DEFAULT_TEAM_ID},
            )


def downgrade() -> None:
    """Set team_id back to NULL for default team rows."""
    conn = op.get_bind()
    tables_with_team_id = [
        "drafts", "plans", "publish_log", "brand_settings",
        "mentions", "saved_blends", "platform_tokens", "post_metrics",
    ]
    for table in tables_with_team_id:
        if _table_exists(table) and _column_exists(table, "team_id"):
            conn.execute(
                sa.text(f"UPDATE {table} SET team_id = NULL WHERE team_id = :tid"),
                {"tid": DEFAULT_TEAM_ID},
            )
    conn.execute(
        sa.text("DELETE FROM team_members WHERE team_id = :tid"),
        {"tid": DEFAULT_TEAM_ID},
    )
    conn.execute(
        sa.text("DELETE FROM teams WHERE team_id = :tid"),
        {"tid": DEFAULT_TEAM_ID},
    )
