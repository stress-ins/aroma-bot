#!/usr/bin/env python3
"""Bulk recovery of KIE image generation tasks.

Queries KIE API for all completed tasks and downloads images
that were lost due to the result_urls parsing bug.

Usage:
    .venv/bin/python scripts/recover_kie_tasks.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_KIE_BASE_URL = "https://api.kie.ai/api/v1/jobs"
_PAGE_SIZE = 50


def fetch_tasks(headers: dict[str, str], page: int = 1) -> dict:
    """Fetch a page of tasks from KIE API."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{_KIE_BASE_URL}/recordList",
            headers=headers,
            params={"page": page, "size": _PAGE_SIZE},
        )
    resp.raise_for_status()
    return resp.json()


def extract_image_url(task: dict) -> str | None:
    """Extract image URL from a task record, handling both formats."""
    result_json_raw = task.get("resultJson", "")
    try:
        result_obj = json.loads(result_json_raw) if isinstance(result_json_raw, str) else result_json_raw
    except (json.JSONDecodeError, TypeError):
        result_obj = {}

    if isinstance(result_obj, dict):
        urls = result_obj.get("resultUrls", [])
        if not urls:
            inner_data = result_obj.get("data", {})
            if isinstance(inner_data, dict):
                urls = inner_data.get("result_urls", []) or inner_data.get("resultUrls", [])
        if urls:
            return urls[0]

    for key in ("resultImageUrl", "resultImage", "imageUrl", "url"):
        if task.get(key):
            return task[key]

    return None


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Recover KIE image generation results")
    parser.add_argument("--dry-run", action="store_true", help="Only list tasks, don't download")
    parser.add_argument("--limit", type=int, default=0, help="Max tasks to process (0=all)")
    parser.add_argument("--output-dir", type=str, default="data/recovered_kie", help="Output directory")
    args = parser.parse_args()

    kie_key = settings.kie_ai_api_key
    if not kie_key:
        logger.error("No KIE API key configured (KIE_AI_API_KEY)")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"}
    output_dir = Path(args.output_dir)
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    page = 1
    total_found = 0
    total_recovered = 0
    total_already_empty = 0
    processed = 0

    logger.info("Starting KIE task recovery scan...")

    while True:
        try:
            data = fetch_tasks(headers, page)
        except Exception as exc:
            logger.error("Failed to fetch page %d: %s", page, exc)
            break

        inner = data.get("data", {})
        records = inner.get("records", []) if isinstance(inner, dict) else []
        total = inner.get("total", 0) if isinstance(inner, dict) else 0

        if not records:
            break

        for task in records:
            task_id = task.get("taskId", "unknown")
            state = task.get("state", "")
            model = task.get("model", "")

            if state != "success":
                continue

            total_found += 1
            image_url = extract_image_url(task)

            if not image_url:
                total_already_empty += 1
                logger.debug("Task %s: success but no URL extractable", task_id)
                continue

            if args.dry_run:
                logger.info("Task %s [%s]: URL=%s", task_id, model, image_url[:80])
                total_recovered += 1
            else:
                img_bytes = download_image(image_url)
                if img_bytes:
                    filename = f"{task_id}.png"
                    (output_dir / filename).write_bytes(img_bytes)
                    total_recovered += 1
                    logger.info("Recovered %s (%d bytes)", task_id, len(img_bytes))
                else:
                    logger.warning("Task %s: URL found but download failed", task_id)

            processed += 1
            if args.limit and processed >= args.limit:
                break

        if args.limit and processed >= args.limit:
            break

        logger.info("Page %d: %d records (total in API: %d)", page, len(records), total)
        if page * _PAGE_SIZE >= total:
            break
        page += 1
        time.sleep(0.5)

    logger.info(
        "Done. Success tasks: %d, recovered: %d, no URL: %d",
        total_found, total_recovered, total_already_empty,
    )
    if not args.dry_run and total_recovered:
        logger.info("Images saved to: %s", output_dir.resolve())


if __name__ == "__main__":
    main()
