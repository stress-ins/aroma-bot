"""Background generation tasks for carousel drafts."""
from __future__ import annotations

import asyncio

from bot.handlers.carousel import _generate_carousel_sync
from bot.services.carousel_assets import (
    populate_carousel_slide_assets,
    regenerate_all_carousel_slide_assets,
    regenerate_carousel_slide_asset,
)
from bot.services.drafts_store import get_draft, update_draft
from bot.services.forbidden_phrases import load_forbidden_phrases

from ._common import _run_generation_task, set_generation_state


async def complete_carousel_generation(draft_id: str, topic: str, blend_context: dict | None = None) -> None:
    try:
        loop = asyncio.get_running_loop()
        forbidden = load_forbidden_phrases()
        slides, img_prompts, _angle, _hook = await loop.run_in_executor(
            None, _generate_carousel_sync, topic, forbidden, blend_context
        )
        if not slides:
            raise RuntimeError("carousel_generation_failed")
        draft = await get_draft(draft_id)
        if not draft:
            return
        payload = dict(draft.payload or {})
        payload.update(
            {
                "slides": slides,
                "img_prompts": img_prompts,
                "arc": "",
                "slide_images": [],
                "slide_image_versions": [],
                "img_prompt_notes": [],
                "images_ready": 0,
                "generation_pending": True,
                "generation_stage": "images",
                "generation_message": "Генерирую картинки для слайдов.",
            }
        )
        if blend_context:
            payload["blend_context"] = blend_context
        await update_draft(draft_id, payload=payload, status="draft")
        await populate_carousel_slide_assets(draft_id)
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось закончить генерацию карусели. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_carousel_regen_slide(
    draft_id: str, slide_index: int, note: str | None = None
) -> None:
    """Regenerate image for a single carousel slide as a background task."""
    try:
        result = await regenerate_carousel_slide_asset(draft_id, slide_index, note=note)
        if result is None:
            raise RuntimeError("carousel_slide_regenerate_failed")
        draft = await get_draft(draft_id)
        if draft:
            payload = dict(draft.payload)
            payload["regen_count"] = payload.get("regen_count", 0) + 1
            await update_draft(draft_id, payload=payload)
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось перегенерировать картинку. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_carousel_regenerate_all(draft_id: str) -> None:
    await _run_generation_task(
        draft_id,
        regenerate_all_carousel_slide_assets(draft_id),
        "Не удалось перегенерировать все картинки. Попробуйте ещё раз.",
    )
