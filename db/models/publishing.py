from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, JSON
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class PublishLogModel(Base):
    __tablename__ = "publish_log"
    __table_args__ = (
        Index("ix_publish_log_draft_created", "draft_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32))  # "threads" | "instagram" | "telegram"
    action: Mapped[str] = mapped_column(String(32))  # "publish" | "schedule" | "cancel"
    status: Mapped[str] = mapped_column(String(32), default="pending")  # "pending" | "success" | "failed"
    external_id: Mapped[str] = mapped_column(String(255), default="")
    error_message: Mapped[str] = mapped_column(String(1000), default="")
    attempt_num: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PastPublicationModel(Base):
    __tablename__ = "past_publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    pub_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    draft_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    # Post identity
    platform: Mapped[str] = mapped_column(String(32), index=True)  # threads/instagram/telegram/tiktok
    kind: Mapped[str] = mapped_column(String(64), default="text")  # text/carousel/reels/stories
    external_url: Mapped[str] = mapped_column(String(1024), default="")
    external_id: Mapped[str] = mapped_column(String(255), default="")

    # Content
    topic: Mapped[str] = mapped_column(String(255), default="")
    caption: Mapped[str] = mapped_column(String(4000), default="")
    hashtags: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    # Engagement metrics
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)

    # Scoring (1-5, NULL = not rated)
    score_engagement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_brand_fit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_craft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_goal_hit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Tags
    content_pillar: Mapped[str] = mapped_column(String(64), default="")
    funnel_stage: Mapped[str] = mapped_column(String(32), default="")  # awareness/consideration/conversion/retention
    notes: Mapped[str] = mapped_column(String(1000), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
