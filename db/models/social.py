from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, JSON, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class MentionModel(Base):
    __tablename__ = "mentions"

    id: Mapped[int] = mapped_column(primary_key=True)
    mention_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True, default="")
    type: Mapped[str] = mapped_column(String(32), default="mention")
    author_username: Mapped[str] = mapped_column(String(255), default="")
    author_name: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(String(4000), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    context_post: Mapped[str] = mapped_column(String(4000), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)


class MentionReplyModel(Base):
    __tablename__ = "mention_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    reply_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    mention_id: Mapped[str] = mapped_column(String(36), index=True)
    tone: Mapped[str] = mapped_column(String(32), default="warm")
    content: Mapped[str] = mapped_column(String(2000), default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    publish_error: Mapped[str] = mapped_column(String(1000), default="")


class PlatformTokenModel(Base):
    __tablename__ = "platform_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
    access_token: Mapped[str] = mapped_column(String(1024), default="")
    refresh_token: Mapped[str] = mapped_column(String(1024), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (UniqueConstraint("team_id", "platform"),)


class TrackedThreadModel(Base):
    """A brand-relevant Threads conversation found via monitoring."""
    __tablename__ = "tracked_threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(16), default="threads", index=True)
    source: Mapped[str] = mapped_column(String(32), default="mention")
    author_username: Mapped[str] = mapped_column(String(128), default="")
    text: Mapped[str] = mapped_column(String(4000), default="")
    permalink: Mapped[str] = mapped_column(String(512), default="")
    root_text: Mapped[str] = mapped_column(String(4000), default="")
    keyword_matched: Mapped[str] = mapped_column(String(128), default="")
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    relevance_score: Mapped[float] = mapped_column(default=0.0)
    relevance_reason: Mapped[str] = mapped_column(String(500), default="")
    suggested_action: Mapped[str] = mapped_column(String(32), default="")
    ai_summary: Mapped[str] = mapped_column(String(1000), default="")
    content_angle: Mapped[str] = mapped_column(String(500), default="")
    topic_tags: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    found_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class SocialTrendPostModel(Base):
    """Stores individual collected posts from monitored competitor accounts."""
    __tablename__ = "social_trend_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.team_id"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(16), index=True)  # instagram | threads
    source_type: Mapped[str] = mapped_column(String(16))  # account | hashtag
    source_value: Mapped[str] = mapped_column(String(128))  # @username or #tag
    post_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    author_username: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(String, default="")
    permalink: Mapped[str] = mapped_column(String(512), default="")
    media_type: Mapped[str] = mapped_column(String(32), default="")  # TEXT_POST | IMAGE | VIDEO | CAROUSEL_ALBUM
    thumbnail_url: Mapped[str] = mapped_column(String, default="")
    hashtags: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class HashtagQuotaModel(Base):
    """Tracks Instagram hashtag API usage (30 unique tags / 7 days per user)."""
    __tablename__ = "hashtag_quotas"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.team_id"), nullable=True, index=True
    )
    hashtag: Mapped[str] = mapped_column(String(128))
    searched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
