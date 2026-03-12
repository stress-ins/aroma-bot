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


def _prompt_with_note(prompt: str, note: str = "") -> str:
    base = (prompt or _FALLBACK_PROMPT).strip()
    note = note.strip()
    if not note:
        return base
    return f"{base}\n\nRevision note: {note}"


def _slide_dir(draft_id: str) -> Path:
    path = CAROUSEL_ASSETS_DIR / draft_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_slide_versions(
    payload: dict[str, object],
    slide_count: int,
) -> tuple[list[dict | None], list[list[dict[str, str]]]]:
    slide_images: list[dict | None] = list(payload.get("slide_images", []))
    while len(slide_images) < slide_count:
        slide_images.append(None)

    raw_versions = payload.get("slide_image_versions", [])
    versions: list[list[dict[str, str]]] = []
    if isinstance(raw_versions, list):
        for item in raw_versions[:slide_count]:
            if isinstance(item, list):
                versions.append([
                    version
                    for version in item
                    if isinstance(version, dict) and version.get("url") and version.get("filename")
                ])
            else:
                versions.append([])
    while len(versions) < slide_count:
        versions.append([])

    for index in range(slide_count):
        current = slide_images[index]
        current_filename = str(current.get("filename", "")).strip() if isinstance(current, dict) else ""
        if current_filename and not any(str(item.get("filename", "")).strip() == current_filename for item in versions[index]):
            versions[index].append(current)

    return slide_images, versions


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
    slide_images, slide_versions = _ensure_slide_versions(draft.payload, len(img_prompts))

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
                version = save_carousel_slide_asset(draft_id, i, image_bytes, prompt=prompt)
                slide_images[i] = version
                slide_versions[i].append(version)
                changed = True
                logger.info("carousel_assets: slide %d generated for draft %s", i + 1, draft_id)
        except Exception:
            logger.exception("carousel_assets: failed on slide %d for draft %s", i + 1, draft_id)

    if changed:
        payload = dict(draft.payload)
        payload["slide_images"] = slide_images
        payload["slide_image_versions"] = slide_versions
        payload["images_ready"] = sum(1 for img in slide_images if img)
        await update_draft(draft_id, payload=payload)


async def regenerate_carousel_slide_asset(
    draft_id: str,
    slide_index: int,
    *,
    note: str | None = None,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        return None

    img_prompts: list[str] = list(draft.payload.get("img_prompts", []))
    if slide_index < 0 or slide_index >= len(img_prompts):
        return None

    slide_images, slide_versions = _ensure_slide_versions(draft.payload, len(img_prompts))

    notes: list[str] = list(draft.payload.get("img_prompt_notes", []))
    while len(notes) < len(img_prompts):
        notes.append("")
    if note is not None:
        notes[slide_index] = note.strip()

    final_prompt = _prompt_with_note(img_prompts[slide_index], notes[slide_index])
    try:
        image_bytes = generate_gemini_image_sync(
            final_prompt,
            log_context=f"carousel slide regenerate {slide_index + 1}/{len(img_prompts)}",
        )
    except Exception:
        logger.exception("carousel_assets: regenerate failed on slide %d for draft %s", slide_index + 1, draft_id)
        return None

    if not image_bytes:
        return None

    version = save_carousel_slide_asset(draft_id, slide_index, image_bytes, prompt=final_prompt)
    slide_images[slide_index] = version
    slide_versions[slide_index].append(version)
    payload = dict(draft.payload)
    payload["slide_images"] = slide_images
    payload["slide_image_versions"] = slide_versions
    payload["img_prompt_notes"] = notes
    payload["images_ready"] = sum(1 for img in slide_images if img)
    updated = await update_draft(draft_id, payload=payload)
    return dict(updated.payload) if updated else None


async def regenerate_all_carousel_slide_assets(draft_id: str) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        return None

    img_prompts: list[str] = list(draft.payload.get("img_prompts", []))
    slide_images, slide_versions = _ensure_slide_versions(draft.payload, len(img_prompts))
    notes: list[str] = list(draft.payload.get("img_prompt_notes", []))
    while len(notes) < len(img_prompts):
        notes.append("")

    changed = False
    for index, prompt in enumerate(img_prompts):
        final_prompt = _prompt_with_note(prompt, notes[index])
        try:
            image_bytes = generate_gemini_image_sync(
                final_prompt,
                log_context=f"carousel slide regenerate all {index + 1}/{len(img_prompts)}",
            )
        except Exception:
            logger.exception("carousel_assets: regenerate-all failed on slide %d for draft %s", index + 1, draft_id)
            continue
        if not image_bytes:
            continue
        version = save_carousel_slide_asset(draft_id, index, image_bytes, prompt=final_prompt)
        slide_images[index] = version
        slide_versions[index].append(version)
        changed = True

    if not changed:
        return dict(draft.payload)

    payload = dict(draft.payload)
    payload["slide_images"] = slide_images
    payload["slide_image_versions"] = slide_versions
    payload["img_prompt_notes"] = notes
    payload["images_ready"] = sum(1 for img in slide_images if img)
    updated = await update_draft(draft_id, payload=payload)
    return dict(updated.payload) if updated else None


async def select_carousel_slide_version(
    draft_id: str,
    slide_index: int,
    version_index: int,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        return None

    prompts: list[str] = list(draft.payload.get("img_prompts", []))
    if slide_index < 0 or slide_index >= len(prompts):
        return None

    slide_images, slide_versions = _ensure_slide_versions(draft.payload, len(prompts))
    if version_index < 0 or version_index >= len(slide_versions[slide_index]):
        return None

    slide_images[slide_index] = slide_versions[slide_index][version_index]
    payload = dict(draft.payload)
    payload["slide_images"] = slide_images
    payload["slide_image_versions"] = slide_versions
    payload["images_ready"] = sum(1 for img in slide_images if img)
    updated = await update_draft(draft_id, payload=payload)
    return dict(updated.payload) if updated else None


async def delete_carousel_slide_version(
    draft_id: str,
    slide_index: int,
    version_index: int,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        return None

    prompts: list[str] = list(draft.payload.get("img_prompts", []))
    if slide_index < 0 or slide_index >= len(prompts):
        return None

    slide_images, slide_versions = _ensure_slide_versions(draft.payload, len(prompts))
    if version_index < 0 or version_index >= len(slide_versions[slide_index]):
        return None

    removed = slide_versions[slide_index].pop(version_index)
    current = slide_images[slide_index]
    current_filename = str(current.get("filename", "")).strip() if isinstance(current, dict) else ""
    removed_filename = str(removed.get("filename", "")).strip()
    if current_filename and current_filename == removed_filename:
      slide_images[slide_index] = slide_versions[slide_index][-1] if slide_versions[slide_index] else None

    payload = dict(draft.payload)
    payload["slide_images"] = slide_images
    payload["slide_image_versions"] = slide_versions
    payload["images_ready"] = sum(1 for img in slide_images if img)
    updated = await update_draft(draft_id, payload=payload)
    return dict(updated.payload) if updated else None


async def update_carousel_slide_text(
    draft_id: str,
    slide_index: int,
    text: str,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        return None

    slides: list[str] = list(draft.payload.get("slides", []))
    if slide_index < 0 or slide_index >= len(slides):
        return None

    slides[slide_index] = text.strip()
    payload = dict(draft.payload)
    payload["slides"] = slides
    updated = await update_draft(draft_id, payload=payload)
    return dict(updated.payload) if updated else None


async def update_carousel_slide_note(
    draft_id: str,
    slide_index: int,
    note: str,
) -> dict[str, object] | None:
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        return None

    prompts: list[str] = list(draft.payload.get("img_prompts", []))
    if slide_index < 0 or slide_index >= len(prompts):
        return None

    notes: list[str] = list(draft.payload.get("img_prompt_notes", []))
    while len(notes) < len(prompts):
        notes.append("")

    notes[slide_index] = note.strip()
    payload = dict(draft.payload)
    payload["img_prompt_notes"] = notes
    updated = await update_draft(draft_id, payload=payload)
    return dict(updated.payload) if updated else None


def load_carousel_slide_images(draft_id: str, slide_images: list[dict | None]) -> list[bytes | None]:
    images: list[bytes | None] = []
    for item in slide_images:
        if not item:
            images.append(None)
            continue
        filename = str(item.get("filename", "")).strip()
        if not filename:
            images.append(None)
            continue
        path = _slide_dir(draft_id) / filename
        images.append(path.read_bytes() if path.exists() else None)
    return images
