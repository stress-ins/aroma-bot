import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class AromaCardModel(Base):
    __tablename__ = "aroma_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), default="aroma", index=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="herb")
    aliases: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class BlendModel(Base):
    __tablename__ = "blends"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    goal: Mapped[str] = mapped_column(String(512), default="")
    ingredients: Mapped[list[dict[str, Any]]] = mapped_column(MutableList.as_mutable(JSON), default=list)
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


class SavedBlendModel(Base):
    __tablename__ = "saved_blends"

    id: Mapped[int] = mapped_column(primary_key=True)
    saved_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True,
        default=lambda: str(uuid.uuid4())
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    brief: Mapped[str] = mapped_column(String(1000), default="")
    tags: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    oils: Mapped[list[dict[str, Any]]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    total_drops: Mapped[int] = mapped_column(Integer, default=0)
    profile: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    expert_note: Mapped[str] = mapped_column(String(2000), default="")
    application_guide: Mapped[str] = mapped_column(String(1000), default="")
    safety_status: Mapped[str] = mapped_column(String(16), default="safe")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class DailyOilModel(Base):
    __tablename__ = "daily_oils"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # "2026-03-17"
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    fact: Mapped[str] = mapped_column(String(1000), default="")
    daily_practice: Mapped[str] = mapped_column(String(1000), default="")
    reason: Mapped[str] = mapped_column(String(500), default="")
    context: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
