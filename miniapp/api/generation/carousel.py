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

from ._common import set_generation_state


def has_complete_carousel_text(payload: dict | None) -> bool:
    """Whether a draft has a complete text/prompt pair for every slide."""
    payload = payload or {}
    slides = payload.get("slides")
    img_prompts = payload.get("img_prompts")
    if not isinstance(slides, list) or not isinstance(img_prompts, list):
        return False
    if not slides or len(slides) != len(img_prompts):
        return False

    def has_slide_text(slide: object) -> bool:
        if isinstance(slide, str):
            return bool(slide.strip())
        if isinstance(slide, dict):
            return any(
                isinstance(slide.get(key), str) and bool(slide[key].strip())
                for key in ("heading", "body", "text")
            )
        return False

    return all(has_slide_text(slide) for slide in slides) and all(
        isinstance(prompt, str) and bool(prompt.strip()) for prompt in img_prompts
    )


def needs_carousel_text_recovery(payload: dict | None) -> bool:
    """Only rebuild text when no usable slide text remains at all."""
    slides = (payload or {}).get("slides")
    if not isinstance(slides, list) or not slides:
        return True
    for slide in slides:
        if isinstance(slide, str) and slide.strip():
            return False
        if isinstance(slide, dict) and any(
            isinstance(slide.get(key), str) and bool(slide[key].strip())
            for key in ("heading", "body", "text")
        ):
            return False
    return True


async def _finish_carousel_asset_generation(draft_id: str, result: str | None) -> None:
    """Keep callback and failure outcomes reported by the asset service intact."""
    if result == "awaiting_callback":
        await set_generation_state(
            draft_id,
            pending=True,
            stage="awaiting_callback",
            message="Картинки генерируются, ожидаем результат…",
        )
    elif result == "error":
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось сгенерировать картинки. Попробуйте ещё раз.",
            error="carousel_assets_failed",
        )
    else:
        await set_generation_state(draft_id, pending=False)


def _carousel_assets_changed(before: dict, after: dict) -> bool:
    """Detect whether image-only regeneration produced a new saved asset."""
    return (
        before.get("slide_images") != after.get("slide_images")
        or before.get("slide_image_versions") != after.get("slide_image_versions")
    )


async def complete_carousel_generation(
    draft_id: str,
    topic: str,
    blend_context: dict | None = None,
    layout_style: str = "overlay",
    *,
    goal_key: str = "trust",
    emotion: str = "calm",
) -> None:
    try:
        loop = asyncio.get_running_loop()
        forbidden = load_forbidden_phrases()
        render_style = "editorial" if layout_style == "editorial" else "overlay"
        slides, img_prompts, _angle, _hook = await loop.run_in_executor(
            None,
            _generate_carousel_sync,
            topic,
            forbidden,
            blend_context,
            render_style,
            goal_key,
            emotion,
        )
        if not has_complete_carousel_text({"slides": slides, "img_prompts": img_prompts}):
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
        result = await populate_carousel_slide_assets(draft_id, layout_style=layout_style)
        await _finish_carousel_asset_generation(draft_id, result)
    except Exception as exc:
        from bot.services.claude_client import ReplicatePaymentError, ReplicateRateLimitError

        message = (
            "Сервис генерации временно недоступен. Попробуйте позже."
            if isinstance(exc, (ReplicatePaymentError, ReplicateRateLimitError))
            else "Не удалось закончить генерацию карусели. Попробуйте ещё раз."
        )
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message=message,
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
    """Regenerate images, or rebuild text first when a failed draft has none."""
    try:
        draft = await get_draft(draft_id)
        if not draft or draft.kind != "carousel":
            raise RuntimeError("carousel_not_found")

        payload = draft.payload or {}
        if needs_carousel_text_recovery(payload):
            layout_style = payload.get("layout_style", "overlay")
            await complete_carousel_generation(
                draft_id,
                draft.topic,
                payload.get("blend_context"),
                layout_style,
                goal_key=payload.get("goal_key", "trust") or "trust",
                emotion=payload.get("emotion", "calm") or "calm",
            )
            return

        if not has_complete_carousel_text(payload):
            raise RuntimeError("carousel_image_prompts_missing")

        result = await regenerate_all_carousel_slide_assets(draft_id)
        if result is None:
            raise RuntimeError("carousel_regenerate_all_failed")

        stage = result.get("generation_stage")
        if stage == "error" and any(
            isinstance(image, dict) and image.get("pending_callback")
            for image in result.get("slide_images", [])
        ):
            await set_generation_state(
                draft_id, pending=True, stage="error",
                message="Часть картинок не удалось создать. Ожидаем остальные результаты…",
                error="carousel_assets_failed",
            )
            return
        if stage not in ("awaiting_callback", "error") and not _carousel_assets_changed(payload, result):
            raise RuntimeError("carousel_regenerate_all_failed")
        await _finish_carousel_asset_generation(draft_id, stage)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось перегенерировать все картинки. Попробуйте ещё раз.",
            error=str(exc),
        )
