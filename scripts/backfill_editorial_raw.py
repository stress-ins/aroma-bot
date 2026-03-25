#!/usr/bin/env python3
"""Backfill raw (text-free) images for editorial carousel drafts.

For editorial drafts generated before the raw_filename feature,
re-generates original images from saved prompts via the image API
and saves them as raw assets.

Usage:
    .venv/bin/python scripts/backfill_editorial_raw.py --dry-run
    .venv/bin/python scripts/backfill_editorial_raw.py
"""
from __future__ import annotations

import argparse
import asyncio
import functools
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.services.drafts_store import list_recent_drafts, update_draft
from bot.services.carousel_assets import save_carousel_slide_asset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def backfill(dry_run: bool = True) -> None:
    drafts = await list_recent_drafts(kind="carousel", limit=500)
    editorial_drafts = [d for d in drafts if d.payload.get("layout_style") == "editorial"]
    logger.info("Found %d editorial drafts out of %d total", len(editorial_drafts), len(drafts))

    if not editorial_drafts:
        return

    updated = 0
    skipped = 0
    failed = 0

    for draft in editorial_drafts:
        slide_images = list(draft.payload.get("slide_images", []))
        img_prompts = list(draft.payload.get("img_prompts", []))
        changed = False

        for i, item in enumerate(slide_images):
            if not isinstance(item, dict) or not item.get("filename"):
                continue
            if item.get("raw_filename"):
                skipped += 1
                continue

            prompt = img_prompts[i] if i < len(img_prompts) else ""
            if not prompt:
                logger.warning("Draft %s slide %d: no prompt, skipping", draft.draft_id, i)
                failed += 1
                continue

            logger.info("Draft %s slide %d: regenerating raw image from prompt [%s...]", draft.draft_id, i, prompt[:50])

            if dry_run:
                logger.info("  [DRY RUN] would regenerate and save raw image")
                continue

            try:
                from bot.services.gemini_images import generate_gemini_image_sync
                result = await asyncio.get_running_loop().run_in_executor(
                    None,
                    functools.partial(
                        generate_gemini_image_sync,
                        prompt,
                        aspect_ratio="4:5",
                        log_context=f"backfill slide {i + 1} draft {draft.draft_id}",
                    ),
                )
                if not result.image_bytes:
                    logger.warning("Draft %s slide %d: generation returned no image: %s", draft.draft_id, i, result.error)
                    failed += 1
                    continue

                raw_version = save_carousel_slide_asset(
                    draft.draft_id, i, result.image_bytes, prompt=prompt,
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
