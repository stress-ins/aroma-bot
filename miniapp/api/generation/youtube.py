"""Background generation tasks for YouTube video drafts."""
from __future__ import annotations

import asyncio
import logging

from bot.agents.broll_director import (
    broll_map_to_payload,
    extract_broll_from_sections,
    generate_broll_map_sync,
)
from bot.agents.youtube_metadata_agent import (
    generate_youtube_metadata_sync,
    metadata_to_payload,
)
from bot.agents.youtube_script_agent import (
    generate_youtube_script_sync,
    script_to_payload,
)
from bot.services.drafts_store import get_draft, update_draft
from bot.services.miniapp_references import build_reference_context
from bot.services.thumbnail_generator import (
    build_thumbnail_payload,
    generate_thumbnail_image,
    generate_thumbnail_prompt_sync,
)

from ._common import set_generation_state

logger = logging.getLogger(__name__)


async def complete_youtube_generation(
    draft_id: str,
    topic: str,
    subformat: str = "talking_head",
    goal: str = "trust",
    emotion: str = "calm",
    duration_target: int = 10,
    *,
    item_count: int = 7,
    question_count: int = 6,
    guest_description: str = "",
) -> None:
    """Full YouTube generation pipeline:
    1. Generate script (with B-roll markers)
    2. Extract/enrich B-Roll Map
    3. Generate thumbnail prompt
    4. Update draft
    """
    try:
        loop = asyncio.get_running_loop()

        logger.info(
            "youtube generation started: draft_id=%s topic=%s subformat=%s",
            draft_id, topic, subformat,
        )

        # Stage 1: Generate script
        await set_generation_state(
            draft_id,
            pending=True,
            stage="script",
            message="Пишу сценарий YouTube-видео.",
        )

        reference_context = await build_reference_context()

        script = await loop.run_in_executor(
            None,
            lambda: generate_youtube_script_sync(
                topic=topic,
                subformat=subformat,
                goal=goal,
                emotion=emotion,
                duration_target=duration_target,
                reference_context=reference_context,
                item_count=item_count,
                question_count=question_count,
                guest_description=guest_description,
            ),
        )

        if not script.sections:
            await set_generation_state(
                draft_id,
                pending=False,
                stage="error",
                message="Генерация вернула пустой сценарий. Попробуйте ещё раз.",
                error="empty sections from youtube script agent",
            )
            return

        logger.info(
            "youtube script ready: draft_id=%s title=%r sections=%d",
            draft_id, script.title, len(script.sections),
        )

        # Stage 2: B-Roll Map
        await set_generation_state(
            draft_id,
            pending=True,
            stage="broll",
            message="Создаю карту B-Roll вставок.",
        )

        script_payload = script_to_payload(script)

        # Quick extraction from sections first
        broll_cues = extract_broll_from_sections(script_payload["sections"])

        # Enrich with Claude if we have cues
        if broll_cues:
            try:
                enriched = await loop.run_in_executor(
                    None,
                    generate_broll_map_sync,
                    script.raw_text,
                )
                if enriched:
                    broll_cues = enriched
            except Exception:
                logger.warning("B-Roll enrichment failed, using basic cues", exc_info=True)

        broll_payload = broll_map_to_payload(broll_cues)

        # Stage 3: Thumbnail prompt
        await set_generation_state(
            draft_id,
            pending=True,
            stage="thumbnail",
            message="Генерирую обложку видео.",
        )

        try:
            thumb_result = await loop.run_in_executor(
                None,
                generate_thumbnail_prompt_sync,
                topic,
                script.title,
                subformat,
                emotion,
            )
            thumbnail_payload = build_thumbnail_payload(
                mode="prompt",
                prompt=thumb_result.get("prompt", ""),
                text_overlay=thumb_result.get("text_overlay", ""),
            )
        except Exception:
            logger.warning("Thumbnail prompt generation failed", exc_info=True)
            thumbnail_payload = build_thumbnail_payload(mode="prompt")

        # Stage 4: Update draft with all generated content
        draft = await get_draft(draft_id)
        if not draft:
            return

        payload = dict(draft.payload or {})
        payload.update(script_payload)
        payload["broll_map"] = broll_payload
        payload["thumbnail"] = thumbnail_payload
        payload["generation_pending"] = False
        payload["generation_stage"] = ""
        payload["generation_message"] = ""

        await update_draft(draft_id, payload=payload, status="draft")
        await set_generation_state(draft_id, pending=False)

        logger.info("youtube generation complete: draft_id=%s", draft_id)

    except Exception as exc:
        logger.exception("youtube generation failed: draft_id=%s", draft_id)
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось сгенерировать YouTube-видео. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_youtube_regen_script(
    draft_id: str,
    revision_note: str = "",
) -> None:
    """Regenerate script only, keeping B-roll map and thumbnail."""
    try:
        draft = await get_draft(draft_id)
        if not draft:
            return

        payload = dict(draft.payload or {})
        topic = draft.topic
        subformat = payload.get("subformat", "talking_head")
        goal = payload.get("goal", "trust")
        emotion = payload.get("emotion", "calm")
        duration_target = payload.get("duration_target", 10)

        # Append revision note to topic context if provided
        effective_topic = topic
        if revision_note:
            effective_topic = f"{topic}\n\nЗамечания к переработке сценария: {revision_note}"

        loop = asyncio.get_running_loop()
        reference_context = await build_reference_context()

        script = await loop.run_in_executor(
            None,
            lambda: generate_youtube_script_sync(
                topic=effective_topic,
                subformat=subformat,
                goal=goal,
                emotion=emotion,
                duration_target=duration_target,
                reference_context=reference_context,
            ),
        )

        script_payload = script_to_payload(script)
        payload.update(script_payload)

        # Re-extract B-roll from new script
        broll_cues = extract_broll_from_sections(script_payload["sections"])
        payload["broll_map"] = broll_map_to_payload(broll_cues)

        if revision_note:
            payload["last_revision_note"] = revision_note

        await update_draft(draft_id, payload=payload)
        await set_generation_state(draft_id, pending=False)

    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Ошибка перегенерации сценария.",
            error=str(exc),
        )


async def complete_youtube_generate_thumbnail(
    draft_id: str,
    mode: str = "prompt",
    revision_note: str = "",
    source_photo_path: str = "",
) -> None:
    """Generate or regenerate thumbnail for a YouTube draft."""
    try:
        draft = await get_draft(draft_id)
        if not draft:
            return

        payload = dict(draft.payload or {})
        topic = draft.topic
        title = payload.get("title", topic)
        subformat = payload.get("subformat", "talking_head")
        emotion = payload.get("emotion", "calm")

        loop = asyncio.get_running_loop()
        current_thumb = payload.get("thumbnail", {})

        if mode == "prompt":
            if revision_note and current_thumb.get("prompt"):
                from bot.services.thumbnail_generator import revise_thumbnail_prompt_sync
                result = await loop.run_in_executor(
                    None,
                    revise_thumbnail_prompt_sync,
                    current_thumb["prompt"],
                    revision_note,
                )
            else:
                result = await loop.run_in_executor(
                    None,
                    generate_thumbnail_prompt_sync,
                    topic, title, subformat, emotion,
                )

            # Generate image
            image_path = await generate_thumbnail_image(
                result.get("prompt", ""),
                draft_id,
            )

            # Save history
            history = current_thumb.get("history", [])
            if current_thumb.get("result_path"):
                history.append({
                    "prompt": current_thumb.get("prompt", ""),
                    "note": revision_note,
                    "path": current_thumb.get("result_path", ""),
                })

            payload["thumbnail"] = build_thumbnail_payload(
                mode="prompt",
                prompt=result.get("prompt", ""),
                text_overlay=result.get("text_overlay", ""),
                result_path=image_path,
                revision_note=revision_note,
            )
            payload["thumbnail"]["history"] = history

        elif mode == "photo_based":
            from bot.services.thumbnail_generator import generate_photo_based_prompt_sync
            if revision_note and current_thumb.get("prompt"):
                from bot.services.thumbnail_generator import revise_thumbnail_prompt_sync
                result = await loop.run_in_executor(
                    None,
                    revise_thumbnail_prompt_sync,
                    current_thumb["prompt"],
                    revision_note,
                )
            else:
                result = await loop.run_in_executor(
                    None,
                    generate_photo_based_prompt_sync,
                    topic, title, emotion,
                )

            image_path = await generate_thumbnail_image(
                result.get("prompt", ""),
                draft_id,
                source_photo_path=source_photo_path,
            )

            history = current_thumb.get("history", [])
            if current_thumb.get("result_path"):
                history.append({
                    "prompt": current_thumb.get("prompt", ""),
                    "note": revision_note,
                    "path": current_thumb.get("result_path", ""),
                })

            payload["thumbnail"] = build_thumbnail_payload(
                mode="photo_based",
                prompt=result.get("prompt", ""),
                text_overlay=result.get("text_overlay", ""),
                result_path=image_path,
                source_photo_path=source_photo_path,
                revision_note=revision_note,
            )
            payload["thumbnail"]["history"] = history

        await update_draft(draft_id, payload=payload)
        await set_generation_state(draft_id, pending=False)

    except Exception as exc:
        logger.exception("Thumbnail generation failed: draft_id=%s", draft_id)
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось сгенерировать обложку.",
            error=str(exc),
        )


async def complete_youtube_generate_metadata(
    draft_id: str,
) -> None:
    """Generate YouTube metadata (title, description, tags, chapters) after montage."""
    try:
        draft = await get_draft(draft_id)
        if not draft:
            return

        payload = dict(draft.payload or {})
        sections_with_durations = payload.get("sections_with_durations", [])
        if not sections_with_durations:
            # Build from sections without real durations
            sections = payload.get("sections", [])
            sections_with_durations = [
                {"label": s.get("label", s.get("section_type", "")), "start_seconds": 0.0}
                for s in sections
            ]

        # Reconstruct scenario text from sections
        scenario_lines = []
        for s in payload.get("sections", []):
            scenario_lines.append(f"[{s.get('section_type', '')}] {s.get('label', '')}")
            text = s.get("speaker_text", "") or s.get("host_text", "")
            if text:
                scenario_lines.append(text)
        scenario_text = "\n\n".join(scenario_lines)

        total_duration = 0.0
        if sections_with_durations:
            last = sections_with_durations[-1]
            total_duration = last.get("start_seconds", 0) + last.get("duration_seconds", 60)

        loop = asyncio.get_running_loop()
        metadata = await loop.run_in_executor(
            None,
            generate_youtube_metadata_sync,
            scenario_text,
            sections_with_durations,
            total_duration,
        )

        payload["metadata"] = metadata_to_payload(metadata)
        await update_draft(draft_id, payload=payload)
        await set_generation_state(draft_id, pending=False)

    except Exception as exc:
        logger.exception("YouTube metadata generation failed: draft_id=%s", draft_id)
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось сгенерировать метаданные для YouTube.",
            error=str(exc),
        )
