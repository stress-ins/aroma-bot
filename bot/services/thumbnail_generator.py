"""Thumbnail generator for YouTube videos — 3 modes + revision iterations.

Modes:
1. AI prompt-based: generate from scratch using image model
2. Photo-based: img2img enhancement of user's photo
3. Upload: user provides a ready-made thumbnail

All modes support iterative revision via revision_note.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import uuid4

from bot.agents.prompts.youtube_prompts import (
    THUMBNAIL_PHOTO_BASED_PROMPT,
    THUMBNAIL_PROMPT,
    THUMBNAIL_REVISION_PROMPT,
)
from bot.services.claude_client import call_claude

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = Path(__file__).parent.parent.parent / "data" / "thumbnails"
THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

# Minimum thumbnail dimensions (YouTube recommended: 1280x720)
MIN_WIDTH = 1280
MIN_HEIGHT = 720
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB


# ---------------------------------------------------------------------------
# Prompt generation helpers
# ---------------------------------------------------------------------------

def _parse_thumbnail_response(raw: str) -> dict:
    """Parse PROMPT: and TEXT_OVERLAY: from Claude response."""
    prompt = ""
    text_overlay = ""
    for line in raw.splitlines():
        clean = line.strip().replace("**", "").strip()
        if clean.startswith("PROMPT:"):
            prompt = clean[len("PROMPT:"):].strip()
        elif clean.startswith("TEXT_OVERLAY:"):
            text_overlay = clean[len("TEXT_OVERLAY:"):].strip()
    return {"prompt": prompt, "text_overlay": text_overlay}


def generate_thumbnail_prompt_sync(
    topic: str,
    title: str,
    subformat: str = "talking_head",
    emotion: str = "calm",
) -> dict:
    """Generate an image prompt for AI thumbnail creation.

    Returns dict with 'prompt' (English) and 'text_overlay' (Russian).
    """
    text = call_claude(
        messages=[{"role": "user", "content": THUMBNAIL_PROMPT.format(
            topic=topic,
            title=title,
            subformat=subformat,
            emotion=emotion,
        )}],
        max_tokens=500,
        context="thumbnail prompt",
    )
    return _parse_thumbnail_response(text)


def revise_thumbnail_prompt_sync(
    previous_prompt: str,
    revision_note: str,
) -> dict:
    """Revise a thumbnail prompt based on user feedback.

    Returns dict with 'prompt' and 'text_overlay'.
    """
    text = call_claude(
        messages=[{"role": "user", "content": THUMBNAIL_REVISION_PROMPT.format(
            previous_prompt=previous_prompt,
            revision_note=revision_note,
        )}],
        max_tokens=500,
        context="thumbnail revision",
    )
    return _parse_thumbnail_response(text)


def generate_photo_based_prompt_sync(
    topic: str,
    title: str,
    emotion: str = "calm",
) -> dict:
    """Generate an img2img prompt for photo-based thumbnail.

    Returns dict with 'prompt' and 'text_overlay'.
    """
    text = call_claude(
        messages=[{"role": "user", "content": THUMBNAIL_PHOTO_BASED_PROMPT.format(
            topic=topic,
            title=title,
            emotion=emotion,
        )}],
        max_tokens=500,
        context="thumbnail photo-based",
    )
    return _parse_thumbnail_response(text)


# ---------------------------------------------------------------------------
# Image generation (delegates to existing image pipeline)
# ---------------------------------------------------------------------------

async def generate_thumbnail_image(
    prompt: str,
    draft_id: str,
    *,
    source_photo_path: str | None = None,
) -> str:
    """Generate a thumbnail image using the configured image model.

    Args:
        prompt: English image prompt.
        draft_id: For organizing output files.
        source_photo_path: If provided, use img2img mode.

    Returns:
        Path to the generated thumbnail file.
    """
    output_dir = THUMBNAIL_DIR / draft_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"thumb_{uuid4().hex[:8]}.jpg"

    try:
        from bot.services.brand_settings_store import get_brand_settings
        bs = await get_brand_settings()

        if source_photo_path:
            # img2img mode
            model = bs.image_model_img2img or "google/nano-banana-edit"
            from bot.services.image_generator import generate_img2img
            result_path = await generate_img2img(
                prompt=prompt,
                source_image=source_photo_path,
                output_path=str(output_path),
                model=model,
                aspect_ratio="16:9",
            )
        else:
            # Text-to-image mode
            model = bs.image_model_carousel or "gpt-image/1.5-text-to-image"
            from bot.services.image_generator import generate_image
            result_path = await generate_image(
                prompt=prompt,
                output_path=str(output_path),
                model=model,
                aspect_ratio="16:9",
            )

        if result_path and Path(result_path).exists():
            logger.info("Thumbnail generated: %s", result_path)
            return str(result_path)

    except Exception:
        logger.warning("Thumbnail generation failed for draft %s", draft_id, exc_info=True)

    return ""


async def save_uploaded_thumbnail(
    draft_id: str,
    file_data: bytes,
    filename: str = "thumbnail.jpg",
) -> str:
    """Save a user-uploaded thumbnail file.

    Returns path to the saved file.
    """
    output_dir = THUMBNAIL_DIR / draft_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine extension from filename
    ext = Path(filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"

    output_path = output_dir / f"thumb_upload_{uuid4().hex[:8]}{ext}"
    output_path.write_bytes(file_data)

    logger.info("Thumbnail uploaded: %s (%d bytes)", output_path, len(file_data))
    return str(output_path)


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def build_thumbnail_payload(
    mode: str,
    prompt: str = "",
    text_overlay: str = "",
    result_path: str = "",
    source_photo_path: str = "",
    revision_note: str = "",
) -> dict:
    """Build the thumbnail sub-payload for DraftModel.payload['thumbnail']."""
    return {
        "mode": mode,  # "prompt" | "photo_based" | "upload"
        "prompt": prompt,
        "text_overlay": text_overlay,
        "result_path": result_path,
        "result_url": f"/generated/thumbnails/{Path(result_path).parent.name}/{Path(result_path).name}" if result_path else "",
        "source_photo_path": source_photo_path,
        "revision_note": revision_note,
        "history": [],
    }
