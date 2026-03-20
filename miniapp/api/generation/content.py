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


async def _build_threads_extra_context(team_id: str | None, topic: str) -> tuple[str, dict]:
    """Gather trending topics and handbook facts for threads series enrichment.

    Returns (extra_context_text, metadata_dict).
    """
    extra_parts: list[str] = []
    metadata: dict = {}

    # Trending topics from monitored accounts (last 7 days)
    if team_id:
        try:
            from bot.services.social_trends_store import get_top_posts
            top_posts = await get_top_posts(team_id, "threads", 7, limit=3)
            if top_posts:
                trends_lines = []
                for p in top_posts:
                    text = (p.get("text") or "")[:120]
                    if text:
                        trends_lines.append(f"- {text}")
                if trends_lines:
                    extra_parts.append("## Актуальные тренды (последние 7 дней)\n" + "\n".join(trends_lines))
                    metadata["trend_source"] = True
        except Exception:
            pass

    # Handbook facts: search oils matching topic keywords
    try:
        from bot.services.miniapp_references import list_reference_cards
        keywords = {w.lower() for w in topic.split() if len(w) > 3}
        if keywords:
            all_cards = await list_reference_cards("oils")
            matched = []
            for c in all_cards:
                card_text = (
                    (c.get("name_ru") or "") + " " +
                    (c.get("name") or "") + " " +
                    (c.get("description_short") or "")
                ).lower()
                if any(kw in card_text for kw in keywords):
                    matched.append(c)
                if len(matched) >= 3:
                    break
            if matched:
                facts_lines = []
                for c in matched:
                    name = c.get("name_ru") or c.get("name") or ""
                    desc = (c.get("description_short") or "")[:100]
                    if name:
                        facts_lines.append(f"- {name}: {desc}" if desc else f"- {name}")
                if facts_lines:
                    extra_parts.append("## Релевантные факты из справочника\n" + "\n".join(facts_lines))
                    metadata["handbook_source"] = True
    except Exception:
        pass

    return "\n\n".join(extra_parts), metadata


async def complete_threads_series_generation(
    draft_id: str,
    topic: str,
    goal_key: str,
    emotion: str = "",
    blend_context: dict | None = None,
    team_id: str | None = None,
) -> None:
    """Background task: generate threads series and update the stub."""
    try:
        from bot.agents import generate_content_draft
        from bot.services.miniapp_generator import build_threads_series_payload

        # Build extra context from trends and handbook
        extra_context, ctx_metadata = await _build_threads_extra_context(team_id, topic)
        enriched_topic = topic
        if extra_context:
            enriched_topic = f"{topic}\n\n{extra_context}\n\nИнструкция: утренний пост может отталкиваться от тренда, дневной — от факта из справочника, вечерний — от личного опыта."

        draft_obj = await generate_content_draft(enriched_topic, goal_key, "threads_series", blend_context=blend_context)
        ts_payload = build_threads_series_payload(draft_obj, goal_key=goal_key, emotion=emotion)
        has_content = any(p.get("text") for p in ts_payload.get("threads_posts", []))
        if not has_content:
            # Retry once with explicit marker instructions
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "threads_series first attempt produced 0 posts for %s, retrying with marker hint", draft_id,
            )
            retry_topic = enriched_topic + "\n\nВАЖНО: используй ТОЧНО три маркера: УТРО, ДЕНЬ, ВЕЧЕР — каждый на отдельной строке."
            draft_obj = await generate_content_draft(retry_topic, goal_key, "threads_series", blend_context=blend_context)
            ts_payload = build_threads_series_payload(draft_obj, goal_key=goal_key, emotion=emotion)
            has_content = any(p.get("text") for p in ts_payload.get("threads_posts", []))
            if not has_content:
                raise RuntimeError("threads_series generation produced 0 posts after retry")
        if blend_context:
            ts_payload["blend_context"] = blend_context
        if ctx_metadata.get("trend_source"):
            ts_payload["trend_source"] = True
        if ctx_metadata.get("handbook_source"):
            ts_payload["handbook_source"] = True
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
