"""Background generation tasks shared across routers and the lifespan hook."""
from __future__ import annotations

import asyncio

from bot.agents.reels_agent import generate_reels_director_sync, generate_reels_scenario_sync
from bot.handlers.carousel import _generate_carousel_sync
from bot.services.carousel_assets import populate_carousel_slide_assets, regenerate_all_carousel_slide_assets
from bot.services.drafts_store import get_draft, update_draft
from bot.services.forbidden_phrases import load_forbidden_phrases
from bot.services.miniapp_references import build_reference_context
from bot.services.reels_assets import populate_reels_frame_assets


async def set_generation_state(
    draft_id: str,
    *,
    pending: bool,
    stage: str = "",
    message: str = "",
    error: str = "",
) -> None:
    draft = await get_draft(draft_id)
    if not draft:
        return
    payload = dict(draft.payload or {})
    payload["generation_pending"] = pending
    payload["generation_stage"] = stage
    payload["generation_message"] = message
    if error:
        payload["generation_error"] = error
    else:
        payload.pop("generation_error", None)
    await update_draft(draft_id, payload=payload, status="draft")


async def complete_carousel_generation(draft_id: str, topic: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        forbidden = load_forbidden_phrases()
        slides, img_prompts, arc = await loop.run_in_executor(
            None, _generate_carousel_sync, topic, forbidden
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
                "arc": arc,
                "slide_images": [],
                "slide_image_versions": [],
                "img_prompt_notes": [],
                "images_ready": 0,
                "generation_pending": True,
                "generation_stage": "images",
                "generation_message": "Генерирую картинки для слайдов.",
            }
        )
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


async def complete_reels_generation(draft_id: str, topic: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        reference_context = await build_reference_context()
        scenario = await loop.run_in_executor(
            None, generate_reels_scenario_sync, topic, reference_context
        )
        await set_generation_state(
            draft_id,
            pending=True,
            stage="storyboard",
            message="Собираю раскадровку рилса.",
        )
        frames = await loop.run_in_executor(None, generate_reels_director_sync, topic, scenario)
        draft = await get_draft(draft_id)
        if not draft:
            return
        payload = dict(draft.payload or {})
        payload.update(
            {
                "scenario": scenario,
                "storyboard": [
                    {
                        "timecode": frame.timecode,
                        "scene": frame.scene,
                        "angle": frame.angle,
                        "gemini_prompt": frame.gemini_prompt,
                        "review_note": "",
                        "prompt_revisions": [],
                        "current_asset": {},
                        "asset_revisions": [],
                    }
                    for frame in frames
                ],
                "images_ready": 0,
                "generation_pending": True,
                "generation_stage": "images",
                "generation_message": "Генерирую кадры для рилса.",
            }
        )
        await update_draft(draft_id, payload=payload, status="draft")
        await populate_reels_frame_assets(draft_id)
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось закончить генерацию рилса. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_carousel_regenerate_all(draft_id: str) -> None:
    try:
        await regenerate_all_carousel_slide_assets(draft_id)
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось перегенерировать все картинки. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_reels_regenerate_all(draft_id: str) -> None:
    try:
        await populate_reels_frame_assets(draft_id, overwrite_existing=True)
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось перегенерировать кадры. Попробуйте ещё раз.",
            error=str(exc),
        )
