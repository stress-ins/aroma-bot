#!/usr/bin/env python3
"""Recover lost KIE-generated images and bind them to draft slides/frames.

Fetches all completed tasks from KIE Playground API, extracts prompts,
matches them to:
  - carousel drafts (img_prompts → slide_images)
  - reels_v2 drafts (image_prompt → image_url)
Downloads the best (newest) image per unique prompt and saves as asset.

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
from bot.services.carousel_assets import save_carousel_slide_asset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# KIE Playground API (different from the jobs API)
_KIE_PLAYGROUND_URL = "https://api.kie.ai/api/v1/playground/pageRecordListByDoris"
_AUTH_TOKEN = "35888dd0-f4d6-422b-9593-8f6dea2e8123"
_UNIQUE_ID = "8faa0c08d720624fb035847b149326a0"
_PAGE_SIZE = 50
# Time window defaults to the last 30 days. Override with --days or --begin/--end.
_DEFAULT_WINDOW_DAYS = 30
_begin_time_ms = 0
_end_time_ms = 0


def _configure_window(days: int | None = None, begin_ms: int | None = None, end_ms: int | None = None) -> tuple[int, int]:
    """Compute the begin/end window in ms since epoch."""
    global _begin_time_ms, _end_time_ms
    if begin_ms and end_ms:
        _begin_time_ms, _end_time_ms = begin_ms, end_ms
    else:
        now_ms = int(time.time() * 1000)
        span = (days or _DEFAULT_WINDOW_DAYS) * 86400 * 1000
        _begin_time_ms, _end_time_ms = now_ms - span, now_ms
    return _begin_time_ms, _end_time_ms


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
                "beginTime": _begin_time_ms,
                "endTime": _end_time_ms,
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


def _download_best_image(
    prompt: str,
    kie_entries: list[tuple[str, int, str]],
    image_cache: dict[str, bytes],
) -> bytes | None:
    """Download best available image for a prompt, with cache."""
    if prompt in image_cache:
        return image_cache[prompt]
    for url, _, tid in kie_entries:
        img_bytes = download_image(url)
        if img_bytes:
            image_cache[prompt] = img_bytes
            return img_bytes
        logger.warning("  Failed to download from task %s, trying next...", tid)
    return None


async def match_and_recover(
    prompt_map: dict[str, list[tuple[str, int, str]]],
    dry_run: bool = False,
) -> None:
    """Match KIE prompts to carousel slides and reels_v2 frames, recover images."""
    image_cache: dict[str, bytes] = {}
    recovered = 0
    failed = 0

    # --- Carousel drafts ---
    carousel_drafts = await list_recent_drafts(limit=500, kind="carousel")
    logger.info("Found %d carousel drafts in DB", len(carousel_drafts))

    for draft in carousel_drafts:
        img_prompts: list[str] = draft.payload.get("img_prompts", [])
        if not img_prompts:
            continue

        raw_images = draft.payload.get("slide_images", [])
        slide_images: list[dict | None] = list(raw_images) if isinstance(raw_images, list) else []
        while len(slide_images) < len(img_prompts):
            slide_images.append(None)

        raw_versions = draft.payload.get("slide_image_versions", [])
        slide_versions: list[list[dict]] = []
        if isinstance(raw_versions, list):
            for item in raw_versions:
                slide_versions.append(list(item) if isinstance(item, list) else [])
        while len(slide_versions) < len(img_prompts):
            slide_versions.append([])

        changed = False
        for idx, prompt in enumerate(img_prompts):
            # Skip slides that already have images
            if slide_images[idx] and isinstance(slide_images[idx], dict) and slide_images[idx].get("url"):
                continue

            prompt_stripped = prompt.strip()
            if not prompt_stripped or prompt_stripped not in prompt_map:
                continue

            kie_entries = prompt_map[prompt_stripped]
            logger.info(
                "Carousel %s slide %d: %d KIE results. Prompt: %.50s...",
                draft.draft_id[:8], idx, len(kie_entries), prompt_stripped[:50],
            )

            if dry_run:
                logger.info("  [DRY-RUN] Would recover slide %d of draft %s", idx, draft.draft_id[:8])
                recovered += 1
                continue

            img_bytes = _download_best_image(prompt_stripped, kie_entries, image_cache)
            if not img_bytes:
                logger.error("  All downloads failed for carousel slide %d", idx)
                failed += 1
                continue

            asset = save_carousel_slide_asset(draft.draft_id, idx, img_bytes, prompt=prompt_stripped)
            slide_images[idx] = asset
            slide_versions[idx].append(asset)
            changed = True
            recovered += 1
            logger.info("  Recovered carousel slide %d → %s", idx, asset["url"])

        if changed and not dry_run:
            payload = dict(draft.payload)
            payload["slide_images"] = slide_images
            payload["slide_image_versions"] = slide_versions
            payload["images_ready"] = sum(1 for img in slide_images if isinstance(img, dict) and img.get("url"))
            payload["generation_pending"] = False
            any_missing = any(
                not (isinstance(img, dict) and img.get("url"))
                for img in slide_images
            )
            payload["generation_stage"] = "error" if any_missing else ""
            updated = await update_draft(draft.draft_id, payload=payload)
            if updated:
                logger.info("  Draft %s updated (%d/%d images ready)",
                            draft.draft_id[:8], payload["images_ready"], len(img_prompts))
            else:
                logger.error("  Failed to update draft %s", draft.draft_id[:8])

    # --- Reels V2 drafts ---
    reels_drafts = await list_recent_drafts(limit=500, kind="reels_v2")
    logger.info("Found %d reels_v2 drafts in DB", len(reels_drafts))

    draft_updates: dict[str, dict] = {}

    for draft in reels_drafts:
        frames = draft.payload.get("frames", [])
        if not isinstance(frames, list):
            continue
        for idx, frame in enumerate(frames):
            if not isinstance(frame, dict):
                continue
            status = frame.get("image_status", "")
            url = str(frame.get("image_url", "")).strip()
            if status == "ready" and url:
                continue

            prompt = frame.get("image_prompt", "").strip()
            if not prompt or prompt not in prompt_map:
                continue

            kie_entries = prompt_map[prompt]
            fid = str(frame.get("id", ""))

            logger.info(
                "ReelsV2 %s frame %s: %d KIE results. Prompt: %.50s...",
                draft.draft_id[:8], fid[:8], len(kie_entries), prompt[:50],
            )

            if dry_run:
                logger.info("  [DRY-RUN] Would recover frame %s (draft %s, idx %d)", fid[:8], draft.draft_id[:8], idx)
                recovered += 1
                continue

            img_bytes = _download_best_image(prompt, kie_entries, image_cache)
            if not img_bytes:
                logger.error("  All downloads failed for frame %s", fid[:8])
                failed += 1
                continue

            asset = save_frame_asset(draft.draft_id, fid, img_bytes, prompt=prompt)

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

            if draft.draft_id not in draft_updates:
                draft_updates[draft.draft_id] = dict(draft.payload)

            frames_list = draft_updates[draft.draft_id].get("frames", [])
            if idx < len(frames_list):
                frames_list[idx] = frame
            draft_updates[draft.draft_id]["frames"] = frames_list

            logger.info("  Recovered frame %s → %s", fid[:8], asset["url"])
            recovered += 1

    if not dry_run and draft_updates:
        logger.info("Persisting updates to %d reels_v2 drafts...", len(draft_updates))
        for draft_id, payload in draft_updates.items():
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
    parser = argparse.ArgumentParser(description="Recover KIE images and bind to carousel/reels_v2 drafts")
    parser.add_argument("--dry-run", action="store_true", help="Show matches without downloading/saving")
    parser.add_argument("--days", type=int, default=_DEFAULT_WINDOW_DAYS,
                        help="How many days back to scan (default: 30)")
    parser.add_argument("--begin-ms", type=int, default=0, help="Explicit begin timestamp (ms since epoch)")
    parser.add_argument("--end-ms", type=int, default=0, help="Explicit end timestamp (ms since epoch)")
    args = parser.parse_args()

    begin, end = _configure_window(
        days=args.days,
        begin_ms=args.begin_ms or None,
        end_ms=args.end_ms or None,
    )
    logger.info("Scanning KIE Playground window: [%d … %d]", begin, end)

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

    logger.info("Step 2: Matching prompts to carousel slides and reels_v2 frames in DB...")
    asyncio.run(match_and_recover(prompt_map, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
