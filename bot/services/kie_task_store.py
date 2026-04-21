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
    """Expire pending KIE tasks older than max_age_minutes.

    Side effect: for every expired task with a draft_id, mark the corresponding
    slot (carousel slide / reels frame) as failed so the UI can render
    "не удалось сгенерировать" instead of an eternal spinner. If the draft has
    no more pending tasks afterwards and at least one slot is still missing an
    image, flip generation_pending=False and generation_stage='error'.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    async with AsyncSessionLocal() as session:
        fetch = await session.execute(
            select(KieTaskModel).where(
                KieTaskModel.status == "pending",
                KieTaskModel.created_at < cutoff,
            )
        )
        tasks = list(fetch.scalars().all())
        if not tasks:
            return 0
        now = datetime.now(timezone.utc)
        for t in tasks:
            t.status = "expired"
            t.completed_at = now
            if not t.error_message:
                t.error_message = "timeout"
        await session.commit()
        # Detach snapshots so we can safely use them after the session closes.
        snapshots = [
            {
                "task_id": t.task_id,
                "draft_id": t.draft_id,
                "content_type": t.content_type,
                "slot_key": t.slot_key,
                "prompt": t.prompt,
            }
            for t in tasks
        ]

    by_draft: dict[str, list[dict]] = {}
    for snap in snapshots:
        draft_id = snap.get("draft_id")
        if draft_id:
            by_draft.setdefault(draft_id, []).append(snap)

    for draft_id, draft_tasks in by_draft.items():
        try:
            await _sync_expired_to_draft(draft_id, draft_tasks)
        except Exception:
            logger.warning("cleanup_expired: failed to sync draft %s", draft_id, exc_info=True)

    return len(snapshots)


async def _sync_expired_to_draft(draft_id: str, expired: list[dict]) -> None:
    """Apply expired-task markers to the given draft payload.

    Read+modify+commit is done inside a single SQLAlchemy session to keep the
    window between reading `payload` and writing it back as small as possible
    (minimises races with concurrent webhook callbacks). SQLite serialises
    writers, so the last committer wins — but since expired tasks are >=30 min
    old, a concurrent webhook for the same draft is rare.
    """
    import copy
    from db.models import DraftModel

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DraftModel).where(DraftModel.draft_id == draft_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return

        # Deep copy so that SQLAlchemy sees `model.payload = payload` as a
        # real assignment and persists it (top-level MutableDict tracks
        # mutations but nested lists/dicts don't — slide_images[i] = marker
        # alone would be missed by the dirty-tracker).
        payload = copy.deepcopy(model.payload or {})
        kind = model.kind
        changed = False

        for snap in expired:
            ctype = snap.get("content_type") or ""
            slot = str(snap.get("slot_key") or "")
            prompt = snap.get("prompt") or ""
            if ctype == "carousel_slide" and kind == "carousel":
                changed = _mark_carousel_slot_failed(payload, slot, prompt) or changed
            elif ctype == "reels_v2_frame" and kind == "reels_v2":
                changed = _mark_reels_v2_frame_failed(payload, slot) or changed
            elif ctype == "reels_frame" and kind == "reels":
                changed = _mark_reels_frame_failed(payload, slot) or changed

        if not changed:
            return

        pending_q = await session.execute(
            select(KieTaskModel).where(
                KieTaskModel.draft_id == draft_id,
                KieTaskModel.status == "pending",
            ).limit(1)
        )
        has_pending = pending_q.scalars().first() is not None

        if not has_pending:
            payload["generation_pending"] = False
            # Clear the stale "Генерирую…" message — the user needs to see
            # the error state, not an in-progress hint.
            if payload.get("generation_message"):
                payload["generation_message"] = ""
            if _any_slot_missing(payload, kind):
                payload["generation_stage"] = "error"
            # else: leave stage as-is (all slots delivered through other paths).

        model.payload = payload
        await session.commit()

    # Wake up SSE listeners so the client re-fetches the carousel detail
    # instead of waiting for the next 3s heartbeat timeout.
    try:
        from miniapp.api.generation._common import _generation_events
        evt = _generation_events.get(draft_id)
        if evt:
            evt.set()
    except Exception:
        logger.debug("cleanup_expired: could not wake SSE listeners", exc_info=True)


def _mark_carousel_slot_failed(payload: dict, slot: str, prompt: str) -> bool:
    try:
        idx = int(slot)
    except (TypeError, ValueError):
        return False

    slide_images = payload.get("slide_images")
    if not isinstance(slide_images, list):
        slide_images = []

    img_prompts = payload.get("img_prompts") or []
    target_len = max(len(img_prompts), idx + 1, len(slide_images))
    while len(slide_images) < target_len:
        slide_images.append(None)

    current = slide_images[idx]
    if isinstance(current, dict) and current.get("url"):
        return False  # slide already delivered (recovery/manual), do not overwrite

    marker = {"failed": True, "error": "timeout"}
    if prompt:
        marker["prompt"] = prompt
    slide_images[idx] = marker
    payload["slide_images"] = slide_images
    return True


def _mark_reels_v2_frame_failed(payload: dict, frame_id: str) -> bool:
    frames = payload.get("frames")
    if not isinstance(frames, list):
        return False
    changed = False
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict):
            continue
        if str(frame.get("id", "")) != frame_id:
            continue
        if str(frame.get("image_url", "")).strip():
            return False
        new_frame = dict(frame)
        new_frame["image_status"] = "error"
        if not new_frame.get("error_message"):
            new_frame["error_message"] = "timeout"
        new_frame.pop("kie_task_id", None)
        frames[i] = new_frame
        payload["frames"] = frames
        changed = True
        break
    return changed


def _mark_reels_frame_failed(payload: dict, slot: str) -> bool:
    try:
        idx = int(slot)
    except (TypeError, ValueError):
        return False
    storyboard = payload.get("storyboard")
    if not isinstance(storyboard, list) or idx >= len(storyboard):
        return False
    frame = storyboard[idx]
    if not isinstance(frame, dict):
        return False
    current = frame.get("current_asset")
    if isinstance(current, dict) and current.get("url"):
        return False
    new_frame = dict(frame)
    new_frame["asset_status"] = "error"
    if not new_frame.get("asset_error"):
        new_frame["asset_error"] = "timeout"
    new_frame.pop("kie_task_id", None)
    storyboard[idx] = new_frame
    payload["storyboard"] = storyboard
    return True


def _any_slot_missing(payload: dict, kind: str) -> bool:
    if kind == "carousel":
        slide_images = payload.get("slide_images") or []
        img_prompts = payload.get("img_prompts") or []
        total = max(len(img_prompts), len(slide_images))
        if total == 0:
            return False
        for i in range(total):
            entry = slide_images[i] if i < len(slide_images) else None
            if not isinstance(entry, dict) or not entry.get("url"):
                return True
        return False
    if kind == "reels_v2":
        frames = payload.get("frames") or []
        for frame in frames:
            if not isinstance(frame, dict):
                return True
            if not str(frame.get("image_url", "")).strip():
                return True
        return False
    if kind == "reels":
        storyboard = payload.get("storyboard") or []
        for frame in storyboard:
            if not isinstance(frame, dict):
                return True
            asset = frame.get("current_asset")
            if not isinstance(asset, dict) or not asset.get("url"):
                return True
        return False
    return False


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
