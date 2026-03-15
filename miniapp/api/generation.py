"""Background generation tasks shared across routers and the lifespan hook."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from uuid import uuid4

from bot.agents.reels_agent import (
    generate_frame_prompts_sync,
    generate_reels_director_sync,
    generate_reels_scenario_sync,
    generate_reels_v2_caption_sync,
    generate_reels_v2_draft_sync,
)
from bot.handlers.carousel import _generate_carousel_sync
from bot.services.carousel_assets import populate_carousel_slide_assets, regenerate_all_carousel_slide_assets
from bot.services.drafts_store import get_draft, update_draft
from bot.services.forbidden_phrases import load_forbidden_phrases
from bot.services.miniapp_references import build_reference_context
from bot.services.reels_assets import populate_frame_assets, populate_reels_frame_assets


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


async def _run_generation_task(
    draft_id: str,
    coro: Awaitable[None],
    error_message: str,
) -> None:
    try:
        await coro
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message=error_message,
            error=str(exc),
        )


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
    """v1 — kept for backward compat and startup recovery."""
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
    await _run_generation_task(
        draft_id,
        regenerate_all_carousel_slide_assets(draft_id),
        "Не удалось перегенерировать все картинки. Попробуйте ещё раз.",
    )


async def complete_reels_regenerate_all(draft_id: str) -> None:
    await _run_generation_task(
        draft_id,
        populate_reels_frame_assets(draft_id, overwrite_existing=True),
        "Не удалось перегенерировать кадры. Попробуйте ещё раз.",
    )


async def complete_reels_v2_generation(
    draft_id: str,
    topic: str,
    goal: str = "trust",
    emotion: str = "calm",
) -> None:
    """Full 4-stage v2 pipeline: concept → frames → caption → images."""
    try:
        loop = asyncio.get_running_loop()

        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion
        )
        await set_generation_state(
            draft_id,
            pending=True,
            stage="frames",
            message="Генерирую кадры для рилса.",
        )

        frame_prompts = await loop.run_in_executor(
            None, generate_frame_prompts_sync, topic, draft_obj.scenario, 4
        )
        frames_payload = [
            {
                "id": uuid4().hex,
                "n": idx,
                "timecode": fp.timecode,
                "overlay_text": fp.overlay_text,
                "image_prompt": fp.image_prompt,
                "image_url": "",
                "image_status": "pending",
                "image_versions": [],
            }
            for idx, fp in enumerate(frame_prompts)
        ]

        await set_generation_state(
            draft_id,
            pending=True,
            stage="caption",
            message="Пишу описание для публикации.",
        )

        caption = await loop.run_in_executor(
            None,
            generate_reels_v2_caption_sync,
            topic,
            draft_obj.concept,
            draft_obj.scenario,
        )

        draft = await get_draft(draft_id)
        if not draft:
            return
        payload = dict(draft.payload or {})
        payload.update(
            {
                "concept": draft_obj.concept,
                "hook": draft_obj.hook,
                "scenario": draft_obj.scenario,
                "caption": caption,
                "music_mood": draft_obj.music_mood,
                "frames": frames_payload,
                "images_ready": 0,
                "generation_pending": True,
                "generation_stage": "images",
                "generation_message": "Генерирую изображения для кадров.",
            }
        )
        await update_draft(draft_id, payload=payload, status="draft")

        await populate_frame_assets(draft_id)
        await set_generation_state(draft_id, pending=False)

    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось закончить генерацию рилса. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_reels_v2_regen_frame(
    draft_id: str,
    frame_id: str,
    prompt: str | None = None,
) -> None:
    """Regenerate image for a single v2 frame."""
    from bot.services.reels_assets import regenerate_frame_asset

    await _run_generation_task(
        draft_id,
        regenerate_frame_asset(draft_id, frame_id, prompt),
        "Не удалось перегенерировать кадр. Попробуйте ещё раз.",
    )


async def complete_reels_v2_regen_concept(
    draft_id: str,
    topic: str,
    goal: str = "trust",
    emotion: str = "calm",
) -> None:
    """Regenerate concept+frames for an existing v2 draft."""
    try:
        loop = asyncio.get_running_loop()

        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion
        )
        await set_generation_state(
            draft_id,
            pending=True,
            stage="frames",
            message="Обновляю кадры рилса.",
        )

        frame_prompts = await loop.run_in_executor(
            None, generate_frame_prompts_sync, topic, draft_obj.scenario, 4
        )
        frames_payload = [
            {
                "id": uuid4().hex,
                "n": idx,
                "timecode": fp.timecode,
                "overlay_text": fp.overlay_text,
                "image_prompt": fp.image_prompt,
                "image_url": "",
                "image_status": "pending",
                "image_versions": [],
            }
            for idx, fp in enumerate(frame_prompts)
        ]

        draft = await get_draft(draft_id)
        if not draft:
            return
        payload = dict(draft.payload or {})
        payload.update(
            {
                "concept": draft_obj.concept,
                "hook": draft_obj.hook,
                "scenario": draft_obj.scenario,
                "frames": frames_payload,
                "images_ready": 0,
                "generation_pending": True,
                "generation_stage": "images",
                "generation_message": "Генерирую изображения для обновлённых кадров.",
            }
        )
        await update_draft(draft_id, payload=payload, status="draft")
        await populate_frame_assets(draft_id)
        await set_generation_state(draft_id, pending=False)

    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось обновить концепцию рилса. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_reels_v2_regen_caption(draft_id: str) -> None:
    """Regenerate caption for a v2 draft."""
    try:
        loop = asyncio.get_running_loop()
        draft = await get_draft(draft_id)
        if not draft or draft.kind != "reels_v2":
            return
        topic = draft.topic
        concept = str(draft.payload.get("concept", ""))
        scenario = str(draft.payload.get("scenario", ""))
        caption = await loop.run_in_executor(
            None,
            generate_reels_v2_caption_sync,
            topic,
            concept,
            scenario,
        )
        from bot.services.miniapp_reels import update_caption
        await update_caption(draft_id, caption)
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось обновить описание. Попробуйте ещё раз.",
            error=str(exc),
        )
