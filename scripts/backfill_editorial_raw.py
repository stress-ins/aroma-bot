#!/usr/bin/env python3
"""Backfill raw (text-free) images for editorial carousel drafts.

For editorial drafts generated before the raw_filename feature,
this script finds original image URLs from kie_tasks table,
re-downloads them, and saves as raw assets.

Usage:
    .venv/bin/python scripts/backfill_editorial_raw.py --dry-run
    .venv/bin/python scripts/backfill_editorial_raw.py
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.services.drafts_store import list_recent_drafts, update_draft
from bot.services.carousel_assets import save_carousel_slide_asset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _get_kie_tasks_for_draft(draft_id: str) -> list:
    """Query kie_tasks table for completed tasks of a given draft."""
    from db.session import AsyncSessionLocal
    from db.models import KieTaskModel
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        stmt = (
            select(KieTaskModel)
            .where(KieTaskModel.draft_id == draft_id)
            .where(KieTaskModel.status == "success")
            .where(KieTaskModel.content_type == "carousel_slide")
            .order_by(KieTaskModel.id)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def backfill(dry_run: bool = True) -> None:
    drafts = await list_recent_drafts(kind="carousel", limit=500)
    editorial_drafts = [d for d in drafts if d.payload.get("layout_style") == "editorial"]
    logger.info("Found %d editorial drafts out of %d total", len(editorial_drafts), len(drafts))

    updated = 0
    skipped = 0
    failed = 0

    for draft in editorial_drafts:
        slide_images = list(draft.payload.get("slide_images", []))
        changed = False

        # Get all KIE tasks for this draft
        kie_tasks = await _get_kie_tasks_for_draft(draft.draft_id)
        tasks_by_slot = {}
        for t in kie_tasks:
            tasks_by_slot.setdefault(t.slot_key, []).append(t)

        for i, item in enumerate(slide_images):
            if not isinstance(item, dict) or not item.get("filename"):
                continue
            if item.get("raw_filename"):
                skipped += 1
                continue

            slot_tasks = tasks_by_slot.get(str(i), [])
            task = next((t for t in reversed(slot_tasks) if t.image_url), None)

            if not task:
                logger.warning("Draft %s slide %d: no completed KIE task with image_url, skipping", draft.draft_id, i)
                failed += 1
                continue

            logger.info("Draft %s slide %d: found KIE task %s, url=%s", draft.draft_id, i, task.task_id, task.image_url[:80])

            if dry_run:
                logger.info("  [DRY RUN] would download and save raw image")
                continue

            try:
                from bot.services.gemini_images import _download_image
                img_bytes = _download_image(task.image_url, f"backfill:{draft.draft_id}:{i}")
                if not img_bytes:
                    logger.warning("Draft %s slide %d: download failed", draft.draft_id, i)
                    failed += 1
                    continue

                raw_version = save_carousel_slide_asset(
                    draft.draft_id, i, img_bytes, prompt=item.get("prompt", "backfill_raw"),
                )
                item["raw_filename"] = raw_version["filename"]
                changed = True
                logger.info("Draft %s slide %d: saved raw as %s", draft.draft_id, i, raw_version["filename"])
            except Exception:
                logger.exception("Draft %s slide %d: error", draft.draft_id, i)
                failed += 1

        if changed and not dry_run:
            payload = dict(draft.payload)
            payload["slide_images"] = slide_images
            await update_draft(draft.draft_id, payload=payload)
            updated += 1
            logger.info("Draft %s: updated payload with raw_filename", draft.draft_id)

    logger.info("Done: %d updated, %d skipped (already had raw), %d failed", updated, skipped, failed)


def main():
    parser = argparse.ArgumentParser(description="Backfill raw images for editorial drafts")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
