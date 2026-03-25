import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text, JSON
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class VideoTaskModel(Base):
    """Persistent queue for video processing tasks (clean, compose, etc.).

    Tasks survive server restarts and are picked up by the background worker.
    """

    __tablename__ = "video_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()),
    )
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32))  # "clean" | "compose"
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True,
    )  # pending | running | completed | failed
    step: Mapped[str] = mapped_column(String(40), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON), default=dict,
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KieTaskModel(Base):
    """Tracks KIE.ai image generation tasks for webhook callback delivery."""
    __tablename__ = "kie_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending/success/failed/expired
    draft_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    content_type: Mapped[str] = mapped_column(String(32), default="")  # carousel_slide/reels_frame/reels_v2_frame/telegram/content
    slot_key: Mapped[str] = mapped_column(String(64), default="")  # slide_index or frame_id
    prompt: Mapped[str] = mapped_column(String(4000), default="")
    aspect_ratio: Mapped[str] = mapped_column(String(8), default="1:1")
    model: Mapped[str] = mapped_column(String(100), default="")
    image_url: Mapped[str] = mapped_column(String(1024), default="")
    error_message: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
