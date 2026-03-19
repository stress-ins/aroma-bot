from datetime import datetime, timezone
import uuid
from typing import Any
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, String, JSON, DateTime, Integer, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[int] = mapped_column(BigInteger)  # telegram_id of creator
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TeamMemberModel(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.team_id"), index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(16), default="viewer")  # owner/editor/viewer
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("team_id", "telegram_id"),)


class TeamInviteModel(Base):
    __tablename__ = "team_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.team_id"), index=True)
    created_by: Mapped[int] = mapped_column(BigInteger)  # telegram_id
    role: Mapped[str] = mapped_column(String(16), default="editor")  # role assigned on accept
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    uses_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class DraftModel(Base):
    __tablename__ = "drafts"

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


class PlanModel(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
    raw_text: Mapped[str] = mapped_column(String)
    entries: Mapped[list[dict[str, Any]]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


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
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, index=True)
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
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.team_id"), nullable=True, unique=True)
    brand_voice: Mapped[str] = mapped_column(String(4000), default="")
    forbidden_phrases: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    base_instructions: Mapped[str] = mapped_column(String(4000), default="")
    target_platforms: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    upload_post_user: Mapped[str] = mapped_column(String(255), default="")
    upload_post_api_key: Mapped[str] = mapped_column(String(255), default="")
    # Image generation model preferences
    image_model_carousel: Mapped[str] = mapped_column(String(100), default="gpt-image/1.5-text-to-image")
    image_model_img2img: Mapped[str] = mapped_column(String(100), default="google/nano-banana-edit")
    image_model_reels: Mapped[str] = mapped_column(String(100), default="gpt-image/1.5-text-to-image")
    reels_auto_images: Mapped[bool] = mapped_column(default=False)
    # Monitored social accounts for trend collection
    instagram_accounts: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    threads_accounts: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    # Tracked hashtags for trend monitoring (e.g. ["ароматерапия", "эфирныемасла"])
    tracked_hashtags: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    # City for weather context (daily oil, etc.)
    city_name: Mapped[str] = mapped_column(String(100), default="Москва")
    city_lat: Mapped[float] = mapped_column(Float, default=55.7558)
    city_lon: Mapped[float] = mapped_column(Float, default=37.6173)
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
    payload: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    author: Mapped[str] = mapped_column(String(64), default="user")
    author_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


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


class UserProfile(Base):
    __tablename__ = "user_profiles"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tier: Mapped[str] = mapped_column(String(32), default="free")  # free/student/expert
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    daily_oil_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tier: Mapped[str] = mapped_column(String(32))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    promo_code_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    activated_by: Mapped[str] = mapped_column(String(32), default="manual")  # manual/promo
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tier: Mapped[str] = mapped_column(String(32))  # student/expert
    duration_days: Mapped[int] = mapped_column(Integer)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    uses_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    date: Mapped[str] = mapped_column(String(16))  # "2026-03-15" (UTC date string)
    cards_created: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("telegram_id", "date"),)


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
