#!/usr/bin/env python3
"""One-off migration: mark long-stuck carousel/reels slots as failed.

Runs against the production DB and for every draft where a slot has no image
but the draft is no longer generating (no pending kie_tasks, generation_pending
already False), writes a {"failed": True, "error": "timeout"} marker so the UI
renders the "Не удалось сгенерировать" plate with the "Новый вариант" button
instead of an eternal spinner.

Idempotent: re-running skips slots that already carry failed=True or url.

Usage:
    .venv/bin/python scripts/heal_stuck_carousel_slots.py --dry-run
    .venv/bin/python scripts/heal_stuck_carousel_slots.py
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from bot.services.drafts_store import list_recent_drafts, update_draft
from bot.services.kie_task_store import get_pending_for_draft

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def heal_carousel(dry_run: bool) -> tuple[int, int]:
    """Return (drafts_patched, slots_marked_failed)."""
    drafts = await list_recent_drafts(limit=1000, kind="carousel")
    drafts_patched = 0
    slots_failed = 0

    for draft in drafts:
        payload = dict(draft.payload or {})
        img_prompts = payload.get("img_prompts") or []
        slide_images = list(payload.get("slide_images") or [])
        if not img_prompts:
            continue

        # Pad slide_images to match img_prompts
        while len(slide_images) < len(img_prompts):
            slide_images.append(None)

        # Skip drafts that are still generating.
        if payload.get("generation_pending"):
            continue
        pending = await get_pending_for_draft(draft.draft_id)
        if pending:
            continue

        missing: list[int] = []
        for i, entry in enumerate(slide_images):
            if isinstance(entry, dict) and entry.get("url"):
                continue  # already delivered
            if isinstance(entry, dict) and entry.get("failed"):
                continue  # already marked failed
            missing.append(i)

        if not missing:
            continue

        logger.info(
            "Draft %s: %d/%d slots stuck. Marking as failed.",
            draft.draft_id[:8], len(missing), len(img_prompts),
        )

        for i in missing:
            prompt = img_prompts[i] if i < len(img_prompts) else ""
            marker = {"failed": True, "error": "timeout"}
            if prompt:
                marker["prompt"] = prompt
            slide_images[i] = marker
            slots_failed += 1

        if dry_run:
            drafts_patched += 1
            continue

        payload["slide_images"] = slide_images
        payload["generation_stage"] = "error"
        payload["generation_pending"] = False
        updated = await update_draft(draft.draft_id, payload=payload)
        if updated:
            drafts_patched += 1
            logger.info("  patched")
        else:
            logger.error("  update failed")

    return drafts_patched, slots_failed


async def heal_reels_v2(dry_run: bool) -> tuple[int, int]:
    drafts = await list_recent_drafts(limit=1000, kind="reels_v2")
    drafts_patched = 0
    frames_failed = 0

    for draft in drafts:
        payload = dict(draft.payload or {})
        frames = payload.get("frames") or []
        if not isinstance(frames, list) or not frames:
            continue

        if payload.get("generation_pending"):
            continue
        pending = await get_pending_for_draft(draft.draft_id)
        if pending:
            continue

        changed = False
        local_failed = 0
        new_frames = []
        for frame in frames:
            if not isinstance(frame, dict):
                new_frames.append(frame)
                continue
            url = str(frame.get("image_url", "")).strip()
            status = frame.get("image_status", "")
            if url or status == "error":
                new_frames.append(frame)
                continue
            patched = dict(frame)
            patched["image_status"] = "error"
            if not patched.get("error_message"):
                patched["error_message"] = "timeout"
            patched.pop("kie_task_id", None)
            new_frames.append(patched)
            local_failed += 1
            changed = True

        if not changed:
            continue

        frames_failed += local_failed
        logger.info("Reels_v2 draft %s: patched %d frames.", draft.draft_id[:8], local_failed)

        if dry_run:
            drafts_patched += 1
            continue

        payload["frames"] = new_frames
        payload["generation_stage"] = "error"
        payload["generation_pending"] = False
        updated = await update_draft(draft.draft_id, payload=payload)
        if updated:
            drafts_patched += 1


    return drafts_patched, frames_failed


async def main_async(dry_run: bool) -> None:
    c_drafts, c_slots = await heal_carousel(dry_run)
    r_drafts, r_frames = await heal_reels_v2(dry_run)
    action = "would patch" if dry_run else "patched"
    logger.info("Carousel: %s %d drafts, %d slots", action, c_drafts, c_slots)
    logger.info("Reels_v2: %s %d drafts, %d frames", action, r_drafts, r_frames)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark stuck carousel/reels slots as failed")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.dry_run))


if __name__ == "__main__":
    main()
