from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, JSON
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


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
    theme: Mapped[str] = mapped_column(String(32), default="terracotta")
    # Content pillars for archive scoring
    content_pillars: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
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
