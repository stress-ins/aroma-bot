from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON

from db.models.base import Base


class DraftModel(Base):
    __tablename__ = "drafts"
    __table_args__ = (
        Index("ix_draft_team_created", "team_id", "created_at"),
        Index("ix_draft_team_status", "team_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # telegram_id
    kind: Mapped[str] = mapped_column(String(64))
    topic: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    feedback: Mapped[str] = mapped_column(String(255), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    publish_platforms: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    external_ids: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    revision_notes: Mapped[str] = mapped_column(String(2000), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    error: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DraftRevisionModel(Base):
    __tablename__ = "draft_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    rev_num: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    author: Mapped[str] = mapped_column(String(64), default="user")
    author_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PlanModel(Base):
    __tablename__ = "plans"
    __table_args__ = (
        Index("ix_plan_team_created", "team_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
    raw_text: Mapped[str] = mapped_column(String)
    entries: Mapped[list[dict[str, Any]]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class RepurposeGroupModel(Base):
    """Group of drafts created by repurposing a single source draft."""

    __tablename__ = "repurpose_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.team_id"), nullable=True, index=True,
    )
    source_draft_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    core_message: Mapped[str] = mapped_column(Text, default="")
    key_points: Mapped[list] = mapped_column(
        MutableList.as_mutable(JSON), default=list,
    )
    target_drafts: Mapped[list] = mapped_column(
        MutableList.as_mutable(JSON), default=list,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
    )
