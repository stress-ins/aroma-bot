from datetime import datetime, timezone
import uuid
from typing import Any
from sqlalchemy import String, JSON, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class DraftModel(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(64))
    topic: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    feedback: Mapped[str] = mapped_column(String(255), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    publish_platforms: Mapped[list[str]] = mapped_column(JSON, default=list)
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    revision_notes: Mapped[str] = mapped_column(String(2000), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    error: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PlanModel(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    raw_text: Mapped[str] = mapped_column(String)
    entries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class AromaCardModel(Base):
    __tablename__ = "aroma_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), default="aroma", index=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="herb")
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TodoModel(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(primary_key=True)
    todo_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    text: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PublishLogModel(Base):
    __tablename__ = "publish_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    platform: Mapped[str] = mapped_column(String(32))  # "threads" | "instagram" | "telegram"
    action: Mapped[str] = mapped_column(String(32))  # "publish" | "schedule" | "cancel"
    status: Mapped[str] = mapped_column(String(32), default="pending")  # "pending" | "success" | "failed"
    external_id: Mapped[str] = mapped_column(String(255), default="")
    error_message: Mapped[str] = mapped_column(String(1000), default="")
    attempt_num: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class BrandSettingsModel(Base):
    __tablename__ = "brand_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_voice: Mapped[str] = mapped_column(String(4000), default="")
    forbidden_phrases: Mapped[list[str]] = mapped_column(JSON, default=list)
    base_instructions: Mapped[str] = mapped_column(String(4000), default="")
    target_platforms: Mapped[list[str]] = mapped_column(JSON, default=list)
    upload_post_user: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DraftRevisionModel(Base):
    __tablename__ = "draft_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    rev_num: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    author: Mapped[str] = mapped_column(String(64), default="user")
    note: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class BlendModel(Base):
    __tablename__ = "blends"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    goal: Mapped[str] = mapped_column(String(512), default="")
    ingredients: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    indications: Mapped[str] = mapped_column(String(2000), default="")
    contraindications: Mapped[str] = mapped_column(String(2000), default="")
    compatibility_notes: Mapped[str] = mapped_column(String(2000), default="")
    source_pdf: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
