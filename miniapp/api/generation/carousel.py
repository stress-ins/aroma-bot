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


async def complete_carousel_generation(
    draft_id: str,
    topic: str,
    blend_context: dict | None = None,
    layout_style: str = "overlay",
) -> None:
    try:
        loop = asyncio.get_running_loop()
        forbidden = load_forbidden_phrases()
        render_style = "editorial" if layout_style == "editorial" else "overlay"
        slides, img_prompts, _angle, _hook = await loop.run_in_executor(
            None, _generate_carousel_sync, topic, forbidden, blend_context, render_style
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
        await populate_carousel_slide_assets(draft_id, layout_style=layout_style)
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


def _generate_carousel_caption_sync(topic: str, slides: list[str], angle: str) -> str:
    """Generate a carousel post caption via Claude."""
    from bot.services.claude_client import call_claude
    from bot.services.brand_settings_store import get_brand_settings_cached

    bs = get_brand_settings_cached()
    forbidden_block = (
        "НЕ использовать следующие фразы:\n"
        + "\n".join(f"- {p}" for p in bs.forbidden_phrases)
        if bs.forbidden_phrases
        else ""
    )
    slides_text = "\n".join(
        f"Слайд {i + 1}: {s}" for i, s in enumerate(slides) if s
    )
    prompt = (
        f"{bs.brand_voice}\n\n"
        f"Напиши описание (caption) для карусельного поста в Instagram.\n\n"
        f"Тема: «{topic}»\n"
        f"Угол подачи: {angle}\n\n"
        f"Слайды:\n{slides_text}\n\n"
        f"Требования:\n"
        f"- 2-4 предложения, описывающие суть карусели\n"
        f"- Разговорный тон, от первого лица\n"
        f"- Призыв к действию или вопрос в конце\n"
        f"- 5-8 релевантных хэштегов\n"
        f"- Макс. 2200 символов\n"
        f"- Только текст, без markdown\n"
        f"\n{forbidden_block}"
    )
    return call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        context="carousel caption",
    )


async def complete_carousel_regen_caption(draft_id: str) -> None:
    """Regenerate caption for a carousel draft via AI."""
    try:
        loop = asyncio.get_running_loop()
        draft = await get_draft(draft_id)
        if not draft or draft.kind != "carousel":
            return
        payload = draft.payload or {}
        topic = draft.topic or ""
        slides = payload.get("slides") or []
        angle = str(payload.get("angle", "") or "")
        caption = await loop.run_in_executor(
            None,
            _generate_carousel_caption_sync,
            topic, slides, angle,
        )
        p = dict(payload)
        p["caption"] = caption
        await update_draft(draft_id, payload=p)
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось сгенерировать описание. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_carousel_regenerate_all(draft_id: str) -> None:
    await _run_generation_task(
        draft_id,
        regenerate_all_carousel_slide_assets(draft_id),
        "Не удалось перегенерировать все картинки. Попробуйте ещё раз.",
    )
