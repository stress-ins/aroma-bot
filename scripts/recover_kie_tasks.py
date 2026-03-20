#!/usr/bin/env python3
"""Recover lost KIE-generated images and bind them to reels_v2 frames.

Fetches all completed tasks from KIE Playground API, extracts prompts,
matches them to frames in reels_v2 drafts by image_prompt, downloads
the best (newest) image per unique prompt, and saves it as a frame asset.

Usage:
    .venv/bin/python scripts/recover_kie_tasks.py --dry-run
    .venv/bin/python scripts/recover_kie_tasks.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.services.drafts_store import list_recent_drafts, update_draft
from bot.services.reels_assets import save_frame_asset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# KIE Playground API (different from the jobs API)
_KIE_PLAYGROUND_URL = "https://api.kie.ai/api/v1/playground/pageRecordListByDoris"
_AUTH_TOKEN = "35888dd0-f4d6-422b-9593-8f6dea2e8123"
_UNIQUE_ID = "8faa0c08d720624fb035847b149326a0"
_PAGE_SIZE = 50
# Time window: covers all relevant generations
_BEGIN_TIME = 1773349200000  # 2026-03-10T00:00:00 approx
_END_TIME = 1774040399999    # 2026-03-18T23:59:59 approx


def fetch_playground_page(page: int) -> dict:
    """Fetch one page of records from KIE Playground API."""
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            _KIE_PLAYGROUND_URL,
            headers={
                "Authorization": _AUTH_TOKEN,
                "UniqueId": _UNIQUE_ID,
                "Content-Type": "application/json",
            },
            json={
                "pageNum": page,
                "pageSize": _PAGE_SIZE,
                "beginTime": _BEGIN_TIME,
                "endTime": _END_TIME,
                "successFlag": "",
            },
        )
    resp.raise_for_status()
    return resp.json()


def extract_prompt(task: dict) -> str | None:
    """Extract prompt from KIE task via double JSON parsing: param → input → prompt."""
    param_raw = task.get("param", "")
    try:
        param_obj = json.loads(param_raw) if isinstance(param_raw, str) else param_raw
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(param_obj, dict):
        return None

    input_raw = param_obj.get("input", "")
    try:
        input_obj = json.loads(input_raw) if isinstance(input_raw, str) else input_raw
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(input_obj, dict):
        return None

    prompt = input_obj.get("prompt", "")
    return prompt.strip() if prompt else None


def extract_image_url(task: dict) -> str | None:
    """Extract image URL from task resultJson."""
    result_raw = task.get("resultJson", "")
    try:
        result_obj = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(result_obj, dict):
        return None

    # Try multiple paths
    urls = result_obj.get("resultUrls", [])
    if not urls:
        inner = result_obj.get("data", {})
        if isinstance(inner, dict):
            urls = inner.get("result_urls", []) or inner.get("resultUrls", [])
    if urls and isinstance(urls, list):
        return urls[0]

    # Fallback: direct URL fields on the task itself
    for key in ("resultImageUrl", "resultImage", "imageUrl", "url"):
        val = task.get(key) or result_obj.get(key)
        if val:
            return val
    return None


def fetch_all_kie_tasks() -> dict[str, list[tuple[str, int, str]]]:
    """Fetch all success tasks, group by prompt.

    Returns: {prompt_text: [(image_url, create_time, task_id), ...]} sorted desc by time.
    """
    prompt_map: dict[str, list[tuple[str, int, str]]] = {}
    page = 1

    while True:
        logger.info("Fetching KIE page %d ...", page)
        try:
            data = fetch_playground_page(page)
        except Exception as exc:
            logger.error("Failed to fetch page %d: %s", page, exc)
            break

        inner = data.get("data", {})
        records = inner.get("records", []) if isinstance(inner, dict) else []
        total = inner.get("total", 0) if isinstance(inner, dict) else 0

        if not records:
            logger.info("No records on page %d, stopping.", page)
            break

        for task in records:
            state = task.get("state", "")
            if state != "success":
                continue

            task_id = task.get("taskId", "unknown")
            prompt = extract_prompt(task)
            image_url = extract_image_url(task)
            create_time = task.get("createTime", 0)

            if not prompt or not image_url:
                continue

            prompt_map.setdefault(prompt, []).append((image_url, create_time, task_id))

        logger.info("Page %d: %d records (total: %d)", page, len(records), total)
        if page * _PAGE_SIZE >= total:
            break
        page += 1
        time.sleep(0.3)

    # Sort each prompt group by createTime descending (newest first)
    for prompt in prompt_map:
        prompt_map[prompt].sort(key=lambda x: x[1], reverse=True)

    return prompt_map


def download_image(url: str) -> bytes | None:
    """Download image bytes from URL."""
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url)
        resp.raise_for_status()
        data = resp.content
        if len(data) < 100:
            return None
        return data
    except Exception as exc:
        logger.warning("Download failed for %s: %s", url[:80], str(exc)[:100])
        return None


async def match_and_recover(
    prompt_map: dict[str, list[tuple[str, int, str]]],
    dry_run: bool = False,
) -> None:
    """Match KIE prompts to reels_v2 frames and recover images."""
    drafts = await list_recent_drafts(limit=500, kind="reels_v2")
    logger.info("Found %d reels_v2 drafts in DB", len(drafts))

    # Collect all frames that need images, grouped by prompt
    frames_needing_images: dict[str, list[tuple[str, int, dict, dict]]] = {}
    # {prompt: [(draft_id, frame_idx, frame, draft_payload), ...]}

    for draft in drafts:
        frames = draft.payload.get("frames", [])
        if not isinstance(frames, list):
            continue
        for idx, frame in enumerate(frames):
            if not isinstance(frame, dict):
                continue
            # Skip frames that already have images
            status = frame.get("image_status", "")
            url = str(frame.get("image_url", "")).strip()
            if status == "ready" and url:
                continue

            prompt = frame.get("image_prompt", "").strip()
            if prompt and prompt in prompt_map:
                frames_needing_images.setdefault(prompt, []).append(
                    (draft.draft_id, idx, frame, draft.payload)
                )

    if not frames_needing_images:
        logger.info("No frames found that need recovery (all already have images or no prompt match)")
        return

    logger.info(
        "Found %d unique prompts matching %d frames across drafts",
        len(frames_needing_images),
        sum(len(v) for v in frames_needing_images.values()),
    )

    # For each matching prompt, download the best image once and apply to all matching frames
    recovered = 0
    failed = 0
    # Cache downloaded images by prompt to avoid re-downloading
    image_cache: dict[str, bytes] = {}

    # Group frames by draft_id for batch updates
    draft_updates: dict[str, dict] = {}  # draft_id → payload

    for prompt, frame_entries in frames_needing_images.items():
        kie_entries = prompt_map[prompt]
        best_url, best_time, best_task_id = kie_entries[0]

        logger.info(
            "Prompt (%.60s...): %d KIE results, %d frames to update. Best task: %s",
            prompt[:60], len(kie_entries), len(frame_entries), best_task_id,
        )

        if dry_run:
            for draft_id, idx, frame, _ in frame_entries:
                fid = frame.get("id", "?")[:8]
                logger.info("  [DRY-RUN] Would recover frame %s (draft %s, idx %d)", fid, draft_id[:8], idx)
            recovered += len(frame_entries)
            continue

        # Download image (try best first, then fallbacks)
        img_bytes = None
        for url, _, tid in kie_entries:
            if prompt in image_cache:
                img_bytes = image_cache[prompt]
                break
            img_bytes = download_image(url)
            if img_bytes:
                image_cache[prompt] = img_bytes
                break
            logger.warning("  Failed to download from task %s, trying next...", tid)

        if not img_bytes:
            logger.error("  All download attempts failed for prompt: %.60s...", prompt[:60])
            failed += len(frame_entries)
            continue

        # Apply to all matching frames
        for draft_id, idx, frame, payload in frame_entries:
            fid = str(frame.get("id", ""))
            asset = save_frame_asset(draft_id, fid, img_bytes, prompt=prompt)

            # Build updated frame
            versions = list(frame.get("image_versions", [])) if isinstance(frame.get("image_versions"), list) else []
            old_url = frame.get("image_url", "")
            if old_url:
                versions.append({"url": old_url, "prompt": frame.get("image_prompt", "")})

            frame["image_url"] = asset["url"]
            frame["image_status"] = "ready"
            frame["image_versions"] = versions[-5:]
            frame.pop("kie_task_id", None)
            frame.pop("error_message", None)
            frame.pop("placement_data", None)

            # Track draft for batch update
            if draft_id not in draft_updates:
                # Load fresh payload copy
                draft_updates[draft_id] = dict(payload)

            # Update the frame in the payload
            frames_list = draft_updates[draft_id].get("frames", [])
            if idx < len(frames_list):
                frames_list[idx] = frame
            draft_updates[draft_id]["frames"] = frames_list

            logger.info("  Recovered frame %s (draft %s, idx %d) → %s", fid[:8], draft_id[:8], idx, asset["url"])
            recovered += 1

    # Persist all draft updates
    if not dry_run and draft_updates:
        logger.info("Persisting updates to %d drafts...", len(draft_updates))
        for draft_id, payload in draft_updates.items():
            # Recount images_ready
            frames_list = payload.get("frames", [])
            images_ready = sum(
                1 for f in frames_list
                if isinstance(f, dict) and bool(str(f.get("image_url", "")).strip())
            )
            payload["images_ready"] = images_ready
            updated = await update_draft(draft_id, payload=payload)
            if updated:
                logger.info("  Draft %s updated (%d/%d images ready)", draft_id[:8], images_ready, len(frames_list))
            else:
                logger.error("  Failed to update draft %s", draft_id[:8])

    logger.info("Done. Recovered: %d, Failed: %d", recovered, failed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Recover KIE images and bind to reels_v2 frames")
    parser.add_argument("--dry-run", action="store_true", help="Show matches without downloading/saving")
    args = parser.parse_args()

    logger.info("Step 1: Fetching all KIE tasks from Playground API...")
    prompt_map = fetch_all_kie_tasks()
    logger.info(
        "Fetched %d unique prompts from %d total success tasks",
        len(prompt_map),
        sum(len(v) for v in prompt_map.values()),
    )

    if not prompt_map:
        logger.warning("No successful KIE tasks found. Nothing to recover.")
        return

    for prompt, entries in prompt_map.items():
        logger.info("  Prompt (%.60s...): %d generations", prompt[:60], len(entries))

    logger.info("Step 2: Matching prompts to reels_v2 frames in DB...")
    asyncio.run(match_and_recover(prompt_map, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
