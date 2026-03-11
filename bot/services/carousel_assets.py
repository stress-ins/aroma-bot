"""Carousel slide image generation and storage for the Mini App.

Images are saved to disk and served via /generated/carousel_assets/<draft_id>/<file>.
The draft payload is updated with slide_images: [{url, generated_at, prompt}].
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bot.services.drafts_store import get_draft, update_draft
from bot.services.gemini_images import generate_gemini_image_sync

logger = logging.getLogger(__name__)

CAROUSEL_ASSETS_DIR = Path(
    os.getenv(
        "AROMA_CAROUSEL_ASSETS_DIR",
        Path(__file__).parent.parent.parent / "data" / "carousel_assets",
    )
)
CAROUSEL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

_FALLBACK_PROMPT = (
    "terracotta minimal lifestyle, dried herbs on warm surface, "
    "soft natural light, large negative space for text, "
    "--ar 1:1 --style atmospheric"
)


def _slide_dir(draft_id: str) -> Path:
    path = CAROUSEL_ASSETS_DIR / draft_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_carousel_slide_asset(
    draft_id: str,
    slide_index: int,
    image_bytes: bytes,
    *,
    prompt: str,
) -> dict[str, str]:
    directory = _slide_dir(draft_id)
    generated_at = datetime.now(timezone.utc).isoformat()
    filename = f"slide_{slide_index + 1}_{uuid4().hex[:8]}.png"
    (directory / filename).write_bytes(image_bytes)
    return {
        "filename": filename,
        "generated_at": generated_at,
        "url": f"/generated/carousel_assets/{draft_id}/{filename}",
        "prompt": prompt,
    }


async def populate_carousel_slide_assets(draft_id: str) -> None:
    """Generate Gemini images for all slides that don't have one yet.

    Updates draft payload in-place: adds/fills slide_images list.
    Runs synchronous Gemini calls sequentially (rate-limit safe).
    """
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        return

    img_prompts: list[str] = draft.payload.get("img_prompts", [])
    slide_images: list[dict | None] = list(draft.payload.get("slide_images", []))

    # Pad to match number of slides
    while len(slide_images) < len(img_prompts):
        slide_images.append(None)

    changed = False
    for i, prompt in enumerate(img_prompts):
        if slide_images[i]:
            continue  # already generated
        try:
            image_bytes = generate_gemini_image_sync(
                prompt or _FALLBACK_PROMPT,
                log_context=f"carousel slide {i + 1}/{len(img_prompts)}",
            )
            if image_bytes:
                slide_images[i] = save_carousel_slide_asset(draft_id, i, image_bytes, prompt=prompt)
                changed = True
                logger.info("carousel_assets: slide %d generated for draft %s", i + 1, draft_id)
        except Exception:
            logger.exception("carousel_assets: failed on slide %d for draft %s", i + 1, draft_id)

    if changed:
        payload = dict(draft.payload)
        payload["slide_images"] = slide_images
        payload["images_ready"] = sum(1 for img in slide_images if img)
        await update_draft(draft_id, payload=payload)
