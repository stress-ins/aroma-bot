"""CRUD for kie_tasks — maps KIE.ai taskId to draft context for webhook callbacks."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from db.models import KieTaskModel
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def register_task(
    task_id: str,
    *,
    draft_id: str | None = None,
    content_type: str = "",
    slot_key: str = "",
    prompt: str = "",
    aspect_ratio: str = "1:1",
    model: str = "",
) -> KieTaskModel:
    async with AsyncSessionLocal() as session:
        task = KieTaskModel(
            task_id=task_id,
            draft_id=draft_id,
            content_type=content_type,
            slot_key=slot_key,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            model=model,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


async def complete_task(task_id: str, image_url: str) -> KieTaskModel | None:
    """Mark task as success. Returns None if already completed (idempotent)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KieTaskModel).where(
                KieTaskModel.task_id == task_id,
                KieTaskModel.status == "pending",
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            return None
        task.status = "success"
        task.image_url = image_url
        task.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(task)
        return task


async def fail_task(task_id: str, error: str) -> KieTaskModel | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KieTaskModel).where(
                KieTaskModel.task_id == task_id,
                KieTaskModel.status == "pending",
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            return None
        task.status = "failed"
        task.error_message = error[:1000]
        task.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(task)
        return task


async def get_task(task_id: str) -> KieTaskModel | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KieTaskModel).where(KieTaskModel.task_id == task_id)
        )
        return result.scalar_one_or_none()


async def get_pending_for_draft(draft_id: str) -> list[KieTaskModel]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KieTaskModel).where(
                KieTaskModel.draft_id == draft_id,
                KieTaskModel.status == "pending",
            )
        )
        return list(result.scalars().all())


async def cleanup_expired(max_age_minutes: int = 30) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(KieTaskModel)
            .where(
                KieTaskModel.status == "pending",
                KieTaskModel.created_at < cutoff,
            )
            .values(status="expired", completed_at=datetime.now(timezone.utc))
        )
        await session.commit()
        return result.rowcount  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Sync wrapper for use from thread-pool (generate_gemini_image_sync context)
# ---------------------------------------------------------------------------

def register_task_sync(
    task_id: str,
    *,
    draft_id: str | None = None,
    content_type: str = "",
    slot_key: str = "",
    prompt: str = "",
    aspect_ratio: str = "1:1",
    model: str = "",
) -> None:
    """Fire-and-forget sync wrapper — safe to call from sync thread pool."""
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            register_task(
                task_id,
                draft_id=draft_id,
                content_type=content_type,
                slot_key=slot_key,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                model=model,
            )
        )
        loop.close()
    except Exception as exc:
        logger.debug("register_task_sync failed: %s", exc)


def get_task_sync(task_id: str) -> KieTaskModel | None:
    """Sync wrapper for DB check from poll loop."""
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(get_task(task_id))
        loop.close()
        return result
    except Exception as exc:
        logger.debug("get_task_sync failed: %s", exc)
        return None
