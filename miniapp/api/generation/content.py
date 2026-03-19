"""Background generation tasks for content and threads-series drafts."""
from __future__ import annotations

from bot.services.drafts_store import update_draft

from ._common import set_generation_state


async def complete_content_generation(
    draft_id: str,
    topic: str,
    goal_key: str,
    format_key: str,
    blend_context: dict | None = None,
) -> None:
    """Background task: generate content draft and update the stub."""
    try:
        from bot.agents import generate_content_draft
        from bot.services.miniapp_generator import build_content_payload

        draft_obj = await generate_content_draft(topic, goal_key, format_key, blend_context=blend_context)
        content_payload = build_content_payload(draft_obj, goal_key=goal_key, format_key=format_key)
        if blend_context:
            content_payload["blend_context"] = blend_context
        content_payload["generation_pending"] = False
        content_payload.pop("generation_stage", None)
        content_payload.pop("generation_message", None)
        content_payload.pop("generation_error", None)
        await update_draft(draft_id, payload=content_payload, status="draft")
    except Exception as exc:
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось создать черновик. Попробуйте ещё раз.",
            error=str(exc),
        )


async def complete_threads_series_generation(
    draft_id: str,
    topic: str,
    goal_key: str,
    emotion: str = "",
    blend_context: dict | None = None,
) -> None:
    """Background task: generate threads series and update the stub."""
    try:
        from bot.agents import generate_content_draft
        from bot.services.miniapp_generator import build_threads_series_payload

        draft_obj = await generate_content_draft(topic, goal_key, "threads_series", blend_context=blend_context)
        ts_payload = build_threads_series_payload(draft_obj, goal_key=goal_key, emotion=emotion)
        has_content = any(p.get("text") for p in ts_payload.get("threads_posts", []))
        if not has_content:
            raise RuntimeError("threads_series generation produced 0 posts")
        if blend_context:
            ts_payload["blend_context"] = blend_context
        ts_payload["generation_pending"] = False
        ts_payload.pop("generation_stage", None)
        ts_payload.pop("generation_message", None)
        ts_payload.pop("generation_error", None)
        await update_draft(draft_id, payload=ts_payload, status="draft")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("threads_series generation failed for %s: %s", draft_id, exc)
        await set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось создать серию постов. Попробуйте ещё раз.",
            error=str(exc),
        )
