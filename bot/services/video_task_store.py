"""Video task queue — persistent task storage for video processing.

Tasks are stored in SQLite and survive server restarts.
A background worker picks them up sequentially (1 at a time).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from db.models import VideoTaskModel
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def enqueue_task(
    draft_id: str,
    task_type: str,
    config: dict,
    *,
    team_id: str | None = None,
    video_duration: float | None = None,
) -> VideoTaskModel:
    """Add a new task to the queue. Returns the created task."""
    async with AsyncSessionLocal() as session:
        # Cancel any existing pending/running task of same type for this draft
        await session.execute(
            update(VideoTaskModel)
            .where(
                VideoTaskModel.draft_id == draft_id,
                VideoTaskModel.task_type == task_type,
                VideoTaskModel.status.in_(["pending", "running"]),
            )
            .values(status="cancelled")
        )
        await session.flush()

        task = VideoTaskModel(
            draft_id=draft_id,
            team_id=team_id,
            task_type=task_type,
            status="pending",
            config=config,
            video_duration=video_duration,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


async def claim_next_task() -> VideoTaskModel | None:
    """Claim the oldest pending task. Returns None if queue empty."""
    async with AsyncSessionLocal() as session:
        q = (
            select(VideoTaskModel)
            .where(VideoTaskModel.status == "pending")
            .order_by(VideoTaskModel.created_at.asc())
            .limit(1)
        )
        result = await session.execute(q)
        task = result.scalar_one_or_none()
        if not task:
            return None

        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(task)
        return task


async def update_task_progress(
    task_id: str, *, step: str = "", progress: int = 0,
) -> None:
    """Update step and progress for a running task."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VideoTaskModel)
            .where(VideoTaskModel.task_id == task_id)
            .values(step=step, progress=progress)
        )
        await session.commit()


async def complete_task(
    task_id: str, *, result: dict | None = None,
) -> None:
    """Mark task as completed."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VideoTaskModel)
            .where(VideoTaskModel.task_id == task_id)
            .values(
                status="completed",
                progress=100,
                result=result,
                finished_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def fail_task(task_id: str, *, error: str = "") -> None:
    """Mark task as failed."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VideoTaskModel)
            .where(VideoTaskModel.task_id == task_id)
            .values(
                status="failed",
                error=error,
                finished_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def get_task(task_id: str) -> VideoTaskModel | None:
    """Get a task by ID."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VideoTaskModel).where(VideoTaskModel.task_id == task_id)
        )
        return result.scalar_one_or_none()


async def get_active_task_for_draft(
    draft_id: str, task_type: str,
) -> VideoTaskModel | None:
    """Get the active (pending/running) task for a draft."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VideoTaskModel)
            .where(
                VideoTaskModel.draft_id == draft_id,
                VideoTaskModel.task_type == task_type,
                VideoTaskModel.status.in_(["pending", "running"]),
            )
            .order_by(VideoTaskModel.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def get_queue_position(task_id: str) -> int:
    """Get the position of a task in the queue (0 = currently running)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VideoTaskModel)
            .where(VideoTaskModel.status.in_(["pending", "running"]))
            .order_by(VideoTaskModel.created_at.asc())
        )
        tasks = result.scalars().all()
        for i, t in enumerate(tasks):
            if t.task_id == task_id:
                return i
        return -1


async def recover_interrupted_tasks() -> int:
    """Reset any 'running' tasks back to 'pending' (after server restart)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(VideoTaskModel)
            .where(VideoTaskModel.status == "running")
            .values(status="pending", step="", progress=0)
        )
        await session.commit()
        return result.rowcount or 0


async def pending_count() -> int:
    """Number of pending tasks in queue."""
    from sqlalchemy import func

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count(VideoTaskModel.id))
            .where(VideoTaskModel.status.in_(["pending", "running"]))
        )
        return result.scalar() or 0


def estimate_time_seconds(
    task_type: str, video_duration: float | None, config: dict | None = None,
) -> int:
    """Estimate processing time in seconds based on video duration.

    Coefficients tuned for CPU-only VPS (4GB RAM, no GPU).
    Whisper tiny on CPU runs ~3-5x realtime; ffmpeg adds overhead.
    """
    dur = video_duration or 60.0  # assume 60s if unknown

    if task_type == "clean":
        use_whisper = (config or {}).get("use_whisper", True)
        if use_whisper:
            # Whisper tiny on CPU: ~4x realtime + ffmpeg + overhead
            return int(dur * 5.0 + 60)
        else:
            # Silence detection only (ffmpeg silencedetect + concat)
            return int(dur * 0.5 + 20)
    elif task_type == "compose":
        # Frame rendering + encoding on CPU
        return int(dur * 2.0 + 60)
    return int(dur * 2.0 + 60)
