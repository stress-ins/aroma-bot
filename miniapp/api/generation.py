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
from bot.services.carousel_assets import (
    populate_carousel_slide_assets,
    regenerate_all_carousel_slide_assets,
    regenerate_carousel_slide_asset,
)
from bot.services.drafts_store import get_draft, update_draft
from bot.services.forbidden_phrases import load_forbidden_phrases
from bot.services.miniapp_references import build_reference_context
from bot.services.reels_assets import populate_frame_assets, populate_reels_frame_assets


async def generate_blend_construct(body, telegram_id: int | None = None) -> dict:
    """Generate a blend via 3 parallel agents: expert + doctor + compatibility checker."""
    from bot.agents.aromatherapy_expert import construct_blend_sync
    from bot.agents.compatibility_checker import get_incompatible_oils_sync
    from bot.agents.medical_reviewer import review_blend_sync
    from bot.services.llm_cache import get_cached, make_cache_key, set_cached
    from bot.services.miniapp_references import list_reference_cards

    # Check cache
    effects_str = ",".join(sorted(body.effects)) if body.effects else ""
    custom_str = ",".join(sorted(body.custom_oils)) if body.custom_oils else ""
    cache_key = make_cache_key(
        "blend",
        brief=body.brief.lower().strip(),
        effects=effects_str,
        speed=body.speed,
        application=body.application,
        contraindications=body.contraindications.strip().lower(),
        custom_oils=custom_str,
    )
    cached = await get_cached(cache_key)
    if cached:
        return cached

    reference_context = await build_reference_context(
        categories=("aroma",), max_items_per_category=20, max_total_chars=3000
    )

    loop = asyncio.get_running_loop()

    expert_task = loop.run_in_executor(
        None,
        construct_blend_sync,
        body.brief,
        body.effects,
        body.speed,
        body.application,
        body.contraindications,
        reference_context,
        body.custom_oils or None,
    )
    doctor_task = loop.run_in_executor(
        None,
        review_blend_sync,
        body.brief,
        body.effects,
        body.contraindications,
        reference_context,
    )
    incompat_task = loop.run_in_executor(
        None,
        get_incompatible_oils_sync,
        body.effects,
        body.brief,
    )

    from fastapi import HTTPException

    try:
        expert_result, doctor_result, incompat_result = await asyncio.wait_for(
            asyncio.gather(expert_task, doctor_task, incompat_task),
            timeout=55.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="blend_generation_timeout")

    # Match oils to DB entries
    oils = expert_result.get("oils", [])
    aromas = await list_reference_cards("aroma")
    aroma_map = {}
    for a in aromas:
        name = (a.get("name") or "").lower()
        name_en = (a.get("name_en") or "").lower()
        aroma_map[name] = a
        if name_en:
            aroma_map[name_en] = a

    oils_with_db = []
    for oil in oils:
        name_ru = oil.get("name_ru", "")
        name_en = oil.get("name_en", "")
        match = aroma_map.get(name_ru.lower()) or aroma_map.get(name_en.lower())
        oils_with_db.append({
            **oil,
            "db_id": match.get("id") if match else None,
            "in_db": match is not None,
        })

    result = {
        "title": expert_result.get("title", "Смесь"),
        "oils": oils_with_db,
        "total_drops": sum(o.get("drops", 0) for o in oils_with_db),
        "profile": expert_result.get("profile", {}),
        "expert_note": expert_result.get("explanation", ""),
        "doctor_note": doctor_result.get("summary", ""),
        "safety_status": doctor_result.get("status", "safe"),
        "restrictions": doctor_result.get("restrictions", []),
        "incompatible_oils": incompat_result if isinstance(incompat_result, list) else [],
        "application_guide": expert_result.get("application", ""),
        "tags": expert_result.get("tags", []),
    }

    # Store in cache (7 days, per-user)
    await set_cached(cache_key, "blend", result, ttl_hours=168, telegram_id=telegram_id)

    return result


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
    """Full 4-stage v2 pipeline: concept → frames → caption → images."""
    try:
        loop = asyncio.get_running_loop()

        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion, blend_context
        )
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

        await set_generation_state(draft_id, pending=False)

    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
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
    """Regenerate only the concept text — leaves scenario and frames untouched."""
    try:
        loop = asyncio.get_running_loop()
        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion, blend_context
        )
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

        draft_obj = await loop.run_in_executor(
            None, generate_reels_v2_draft_sync, topic, goal, emotion, blend_context
        )
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
