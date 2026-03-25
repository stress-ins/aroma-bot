from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, JSON, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class PostMetricsModel(Base):
    """Stores engagement metric snapshots for published posts."""

    __tablename__ = "post_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32))  # threads | instagram
    external_id: Mapped[str] = mapped_column(String(255), default="")
    metrics: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), default=dict
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ApiCostLog(Base):
    __tablename__ = "api_cost_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(16), index=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    context: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class TrendSignal(Base):
    __tablename__ = "trend_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(32), index=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    keyword: Mapped[str] = mapped_column(String(255), index=True)
    score_raw: Mapped[float] = mapped_column(default=0.0)
    velocity: Mapped[float] = mapped_column(default=0.0)
    lifecycle_stage: Mapped[str] = mapped_column(String(32), default="")
    convergence_score: Mapped[float] = mapped_column(default=0.0)
    sentiment: Mapped[str] = mapped_column(String(16), default="")
    items_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), default=dict
    )


class TrendCardModel(Base):
    """AI-generated trend card from enriched signals."""

    __tablename__ = "trend_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.team_id"), nullable=True, index=True,
    )
    keyword: Mapped[str] = mapped_column(String(255), index=True, default="")
    title: Mapped[str] = mapped_column(String(500), default="")
    strength: Mapped[float] = mapped_column(Float, default=0.0)
    lifecycle: Mapped[str] = mapped_column(String(32), default="")
    sentiment: Mapped[str] = mapped_column(String(16), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    suggested_formats: Mapped[list] = mapped_column(
        MutableList.as_mutable(JSON), default=list,
    )
    source_signals: Mapped[list] = mapped_column(
        MutableList.as_mutable(JSON), default=list,
    )
    velocity: Mapped[float] = mapped_column(Float, default=0.0)
    convergence: Mapped[float] = mapped_column(Float, default=0.0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
    )


class CollectorHealth(Base):
    __tablename__ = "collector_health"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_open_until: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    last_error: Mapped[str] = mapped_column(String(1000), default="")


class LlmCacheModel(Base):
    __tablename__ = "llm_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    cache_type: Mapped[str] = mapped_column(String(32))  # "blend" | "recommendation"
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    date: Mapped[str] = mapped_column(String(16))  # "2026-03-15" (UTC date string)
    cards_created: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("telegram_id", "date"),)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_team_event_created", "team_id", "event_name", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.team_id"), nullable=True, index=True,
    )
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    event_name: Mapped[str] = mapped_column(String(64), index=True)
    event_category: Mapped[str] = mapped_column(String(32), default="")
    event_data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), default=dict,
    )
    session_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True,
    )
