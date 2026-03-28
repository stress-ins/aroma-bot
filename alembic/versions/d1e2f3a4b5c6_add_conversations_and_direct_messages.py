"""add conversations and direct_messages tables

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7a8b9
Create Date: 2026-03-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.team_id"), nullable=True),
        sa.Column("platform", sa.String(32), nullable=False, server_default="instagram"),
        sa.Column("participant_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("participant_username", sa.String(255), nullable=False, server_default=""),
        sa.Column("participant_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("last_message_preview", sa.String(500), nullable=False, server_default=""),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_conversation_id", "conversations", ["conversation_id"], unique=True)
    op.create_index("ix_conversations_team_id", "conversations", ["team_id"])
    op.create_index("ix_conversations_platform", "conversations", ["platform"])
    op.create_index("ix_conversations_status", "conversations", ["status"])
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])

    op.create_table(
        "direct_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.conversation_id"), nullable=False),
        sa.Column("sender_type", sa.String(16), nullable=False, server_default="user"),
        sa.Column("content", sa.String(4000), nullable=False, server_default=""),
        sa.Column("sent_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("external_id", sa.String(255), nullable=False, server_default=""),
    )
    op.create_index("ix_direct_messages_message_id", "direct_messages", ["message_id"], unique=True)
    op.create_index("ix_direct_messages_conversation_id", "direct_messages", ["conversation_id"])
    op.create_index("ix_direct_messages_sent_at", "direct_messages", ["sent_at"])
    op.create_index("ix_direct_messages_external_id", "direct_messages", ["external_id"])


def downgrade() -> None:
    op.drop_table("direct_messages")
    op.drop_table("conversations")
