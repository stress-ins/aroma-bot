#!/usr/bin/env python3
"""Backfill raw (text-free) images for editorial carousel drafts.

For editorial drafts that were generated before the raw_filename feature,
this script re-downloads original images from KIE Playground API and saves
them as raw assets, then updates the draft payload with raw_filename.

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

from bot.services.drafts_store import list_recent_drafts, update_draft, get_draft
from bot.services.carousel_assets import save_carousel_slide_asset, CAROUSEL_ASSETS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


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

        for i, item in enumerate(slide_images):
            if not isinstance(item, dict) or not item.get("filename"):
                continue
            if item.get("raw_filename"):
                skipped += 1
                continue

            # Try to find raw image via KIE task store
            try:
                from bot.services.kie_task_store import get_tasks_for_draft
                tasks = await get_tasks_for_draft(draft.draft_id)
                slide_tasks = [t for t in tasks if t.slot_key == str(i) and t.image_url]

                if not slide_tasks:
                    logger.warning("Draft %s slide %d: no KIE task found, skipping", draft.draft_id, i)
                    failed += 1
                    continue

                task = slide_tasks[-1]  # latest completed task
                logger.info("Draft %s slide %d: re-downloading from %s", draft.draft_id, i, task.image_url[:80])

                if dry_run:
                    logger.info("  [DRY RUN] would download and save raw image")
                    continue

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
