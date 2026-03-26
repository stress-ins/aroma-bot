"""Background generation tasks for reels drafts (v1 and v2)."""
from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from bot.agents.reels_agent import (
    generate_frame_prompts_sync,
    generate_reels_director_sync,
    generate_reels_scenario_sync,
    generate_reels_v2_caption_sync,
    generate_reels_v2_draft_sync,
)
from bot.services.drafts_store import get_draft, update_draft
from bot.services.miniapp_references import build_reference_context
from bot.services.reels_assets import populate_frame_assets, populate_reels_frame_assets

from ._common import _run_generation_task, set_generation_state

logger = logging.getLogger(__name__)


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
    blend_context: dict | None = None,
) -> None:
    """Full 4-stage v2 pipeline: concept -> frames -> caption -> images."""
    try:
        loop = asyncio.get_running_loop()

        logger.info("reels_v2 generation started: draft_id=%s topic=%s", draft_id, topic)
        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion, blend_context
        )

        if not getattr(draft_obj, "concept", None):
            logger.error(
                "reels_v2 generation returned empty concept: draft_id=%s "
                "hook=%r scenario_len=%d caption_len=%d",
                draft_id,
                getattr(draft_obj, "hook", "")[:50],
                len(getattr(draft_obj, "scenario", "") or ""),
                len(getattr(draft_obj, "caption", "") or ""),
            )
            await set_generation_state(
                draft_id,
                pending=False,
                stage="error",
                message="Генерация вернула пустую концепцию. Попробуйте ещё раз.",
                error="empty concept from generate_reels_v2_draft_sync",
            )
            return

        logger.info("reels_v2 concept ready: draft_id=%s concept_len=%d", draft_id, len(draft_obj.concept))
        await set_generation_state(
            draft_id,
            pending=True,
            stage="frames",
            message="Генерирую кадры для рилса.",
        )

        frame_prompts = await loop.run_in_executor(
            None, generate_frame_prompts_sync, topic, draft_obj.scenario, 4, blend_context
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
            }
        )
        if blend_context:
            payload["blend_context"] = blend_context

        # Check if auto-image generation is enabled
        from bot.services.brand_settings_store import get_brand_settings
        bs = await get_brand_settings()
        auto_images = bs.reels_auto_images if bs.reels_auto_images is not None else False

        if auto_images:
            payload["generation_pending"] = True
            payload["generation_stage"] = "images"
            payload["generation_message"] = "Генерирую изображения для кадров."
            await update_draft(draft_id, payload=payload, status="draft")
            await populate_frame_assets(draft_id)
        else:
            payload["generation_pending"] = False
            payload["generation_stage"] = ""
            payload["generation_message"] = ""
            await update_draft(draft_id, payload=payload, status="draft")

        logger.info("reels_v2 generation complete: draft_id=%s", draft_id)
        await set_generation_state(draft_id, pending=False)

    except Exception as exc:
        logger.exception("reels_v2 generation failed: draft_id=%s", draft_id)
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось закончить генерацию рилса. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_reels_lightweight_generation(
    draft_id: str,
    topic: str,
    goal: str = "trust",
    emotion: str = "calm",
    blend_context: dict | None = None,
) -> None:
    """Lightweight mode: concept + scenario + caption + text shot list. No frames/images."""
    try:
        loop = asyncio.get_running_loop()
        logger.info("reels_lightweight generation started: draft_id=%s topic=%s", draft_id, topic)

        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion, blend_context
        )

        if not getattr(draft_obj, "concept", None):
            await set_generation_state(
                draft_id, pending=False, stage="error",
                message="Генерация вернула пустую концепцию. Попробуйте ещё раз.",
                error="empty concept",
            )
            return

        await set_generation_state(
            draft_id, pending=True, stage="caption",
            message="Пишу описание для публикации.",
        )

        caption = await loop.run_in_executor(
            None, generate_reels_v2_caption_sync,
            topic, draft_obj.concept, draft_obj.scenario,
        )

        # Build simplified shot list from scenario
        scenario_lines = [
            ln.strip() for ln in (draft_obj.scenario or "").split("\n") if ln.strip()
        ]
        production_notes = {
            "required": scenario_lines[:6],
            "optional": [],
        }

        draft = await get_draft(draft_id)
        if not draft:
            return
        payload = dict(draft.payload or {})
        payload.update({
            "concept": draft_obj.concept,
            "hook": draft_obj.hook,
            "scenario": draft_obj.scenario,
            "caption": caption,
            "music_mood": draft_obj.music_mood,
            "lightweight": True,
            "production_notes": production_notes,
            "frames": [],
            "images_ready": 0,
            "generation_pending": False,
            "generation_stage": "",
            "generation_message": "",
        })
        if blend_context:
            payload["blend_context"] = blend_context
        await update_draft(draft_id, payload=payload, status="draft")
        await set_generation_state(draft_id, pending=False)
        logger.info("reels_lightweight generation complete: draft_id=%s", draft_id)

    except Exception as exc:
        logger.exception("reels_lightweight generation failed: draft_id=%s", draft_id)
        await set_generation_state(
            draft_id, pending=False, stage="error",
            message="Не удалось закончить генерацию рилса. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_reels_v2_generate_images(draft_id: str) -> None:
    """Generate images for all v2 frames (manual trigger)."""
    await _run_generation_task(
        draft_id,
        populate_frame_assets(draft_id),
        "Не удалось сгенерировать изображения для кадров. Попробуйте ещё раз.",
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


async def complete_reels_v2_regen_concept_only(
    draft_id: str,
    topic: str,
    goal: str = "trust",
    emotion: str = "calm",
    blend_context: dict | None = None,
) -> None:
    """Regenerate only the concept text -- leaves scenario and frames untouched."""
    try:
        loop = asyncio.get_running_loop()
        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion, blend_context
        )

        if not getattr(draft_obj, "concept", None):
            logger.error("regen_concept_only returned empty concept: draft_id=%s", draft_id)
            await set_generation_state(
                draft_id,
                pending=False,
                stage="error",
                message="Генерация вернула пустую концепцию. Попробуйте ещё раз.",
                error="empty concept from generate_reels_v2_draft_sync",
            )
            return

        draft = await get_draft(draft_id)
        if not draft:
            return
        payload = dict(draft.payload or {})
        payload["concept"] = draft_obj.concept
        payload["hook"] = getattr(draft_obj, "hook", "")
        await update_draft(draft_id, payload=payload)
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Ошибка обновления концепции.",
            error=str(exc),
        )


async def complete_reels_v2_regen_scenario_only(draft_id: str) -> None:
    """Regenerate scenario + frame prompts from current concept. Keep existing frame images."""
    try:
        draft = await get_draft(draft_id)
        if not draft:
            return
        topic = draft.topic
        goal = str(draft.payload.get("goal", "trust")) if isinstance(draft.payload, dict) else "trust"
        emotion = str(draft.payload.get("emotion", "calm")) if isinstance(draft.payload, dict) else "calm"
        blend_context = draft.payload.get("blend_context") if isinstance(draft.payload, dict) else None
        loop = asyncio.get_running_loop()

        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion, blend_context
        )
        scenario = draft_obj.scenario

        await set_generation_state(
            draft_id,
            pending=True,
            stage="frames",
            message="Генерирую кадры для нового сценария.",
        )

        current_frames = draft.payload.get("frames", []) if isinstance(draft.payload, dict) else []
        n_frames = len(current_frames) or 4
        frame_prompts = await loop.run_in_executor(
            None, generate_frame_prompts_sync, topic, scenario, n_frames
        )

        new_frames = []
        for idx, fp in enumerate(frame_prompts):
            old = current_frames[idx] if idx < len(current_frames) else {}
            new_frames.append({
                "id": old.get("id") or uuid4().hex,
                "n": idx,
                "timecode": fp.timecode,
                "overlay_text": fp.overlay_text,
                "image_prompt": fp.image_prompt,
                "image_url": old.get("image_url", ""),
                "image_status": old.get("image_status", "pending"),
                "image_versions": old.get("image_versions", []),
            })

        payload = dict(draft.payload or {})
        payload["scenario"] = scenario
        payload["frames"] = new_frames
        await update_draft(draft_id, payload=payload)
        await set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Ошибка обновления сценария.",
            error=str(exc),
        )


async def complete_reels_v2_regen_concept(
    draft_id: str,
    topic: str,
    goal: str = "trust",
    emotion: str = "calm",
    blend_context: dict | None = None,
) -> None:
    """Regenerate concept+frames for an existing v2 draft."""
    try:
        loop = asyncio.get_running_loop()

        logger.info("reels_v2 generation started: draft_id=%s topic=%s", draft_id, topic)
        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion, blend_context
        )

        if not getattr(draft_obj, "concept", None):
            logger.error("reels_v2 generation returned empty concept: draft_id=%s", draft_id)
            await set_generation_state(
                draft_id,
                pending=False,
                stage="error",
                message="Генерация вернула пустую концепцию. Попробуйте ещё раз.",
                error="empty concept from generate_reels_v2_draft_sync",
            )
            return

        logger.info("reels_v2 concept ready: draft_id=%s concept_len=%d", draft_id, len(draft_obj.concept))
        await set_generation_state(
            draft_id,
            pending=True,
            stage="frames",
            message="Обновляю кадры рилса.",
        )

        frame_prompts = await loop.run_in_executor(
            None, generate_frame_prompts_sync, topic, draft_obj.scenario, 4, blend_context
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
            }
        )

        from bot.services.brand_settings_store import get_brand_settings as _get_bs
        bs = await _get_bs()
        auto_images = bs.reels_auto_images if bs.reels_auto_images is not None else False

        if auto_images:
            payload["generation_pending"] = True
            payload["generation_stage"] = "images"
            payload["generation_message"] = "Генерирую изображения для обновлённых кадров."
            await update_draft(draft_id, payload=payload, status="draft")
            await populate_frame_assets(draft_id)
        else:
            payload["generation_pending"] = False
            await update_draft(draft_id, payload=payload, status="draft")

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
