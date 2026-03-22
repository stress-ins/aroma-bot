"""Background generation tasks for Content Series."""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bot.services.drafts_store import update_draft

from ._common import set_generation_state

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)

_TEMPLATES_PATH = Path(__file__).resolve().parents[3] / "data" / "series_templates.json"

GOAL_GUIDANCE = {
    "sales": "Мягко подводить к заявке на сессию, корпоративный wellness или личную практику.",
    "engagement": "Запускать обсуждение, сохраняемость и репосты без дешевой провокации.",
    "trust": "Показывать глубину подхода, безопасность и бережность работы с состоянием.",
    "authority": "Подсвечивать метод, наблюдения и профессиональную рамку без занудства.",
}

FORMAT_LABELS = {
    "threads_series": "Серия Threads",
    "instagram": "Instagram",
    "telegram": "Telegram",
    "carousel": "Карусель",
}


def _load_templates() -> list[dict]:
    if _TEMPLATES_PATH.exists():
        return json.loads(_TEMPLATES_PATH.read_text())
    return []


def get_series_templates() -> list[dict]:
    return _load_templates()


def _get_template_hint(template_key: str, post_count: int) -> str:
    """Build template hint string for the orchestrator."""
    templates = _load_templates()
    for t in templates:
        if t["key"] == template_key:
            hints = []
            for i, pos in enumerate(t.get("positions", [])[:post_count]):
                hints.append(f"Пост {i + 1} ({pos['role']}): {pos['hint']}")
            return "\n".join(hints)
    return f"Произвольная серия из {post_count} постов"


def _format_outline(outline: dict) -> str:
    """Format outline dict as text for writer prompts."""
    lines = [f"Тема: {outline.get('theme', '')}", f"Итог: {outline.get('summary', '')}", ""]
    for pos in outline.get("positions", []):
        idx = pos["index"] + 1
        lines.append(f"Пост {idx}: {pos.get('title', '')} ({pos.get('role', 'middle')})")
        if pos.get("angle"):
            lines.append(f"  Угол: {pos['angle']}")
    return "\n".join(lines)


def _generate_series_sync(
    topic: str,
    goal_key: str,
    format_key: str,
    post_count: int,
    template_key: str,
    rag_context: str = "",
) -> dict:
    """Synchronous series generation pipeline (runs in thread pool).

    Returns full series payload dict.
    """
    from bot.agents.series_orchestrator import generate_outline_sync
    from bot.agents.series_writer import generate_posts_batch_sync, summarize_posts
    from bot.agents.series_coherence import check_coherence_sync

    template_hint = _get_template_hint(template_key, post_count)

    # Step 1: Generate outline
    outline = generate_outline_sync(
        topic, goal_key, format_key, post_count, template_hint,
        GOAL_GUIDANCE, FORMAT_LABELS, rag_context=rag_context,
    )
    outline_text = _format_outline(outline)

    # Step 2: Generate posts in batches
    positions = outline["positions"]
    all_posts = []

    # Batch 1: first 3 posts (or all if <= 3)
    batch1_positions = positions[:3]
    batch1 = generate_posts_batch_sync(
        topic, goal_key, format_key, outline_text,
        batch1_positions, "", GOAL_GUIDANCE, rag_context=rag_context,
    )
    all_posts.extend(batch1)

    # Batch 2: remaining posts (if any)
    if len(positions) > 3:
        batch2_positions = positions[3:]
        prev_summaries = summarize_posts(all_posts)
        batch2 = generate_posts_batch_sync(
            topic, goal_key, format_key, outline_text,
            batch2_positions, prev_summaries, GOAL_GUIDANCE, rag_context=rag_context,
        )
        all_posts.extend(batch2)

    # Build series_posts array
    series_posts = []
    for i, pos in enumerate(positions):
        post_data = all_posts[i] if i < len(all_posts) else {}
        series_posts.append({
            "index": i,
            "role": pos.get("role", "middle"),
            "title": pos.get("title", f"Пост {i + 1}"),
            "caption": post_data.get("caption", ""),
            "cta": post_data.get("cta", ""),
            "visual_prompt": post_data.get("visual_prompt", ""),
            "hashtags": post_data.get("hashtags", ""),
            "status": "draft",
            "scheduled_at": None,
            "versions": [],
        })

    # Step 3: Coherence check
    coherence = check_coherence_sync(topic, series_posts)

    return {
        "template_key": template_key,
        "post_count": post_count,
        "goal_key": goal_key,
        "format_key": format_key,
        "outline": outline,
        "series_posts": series_posts,
        "coherence_score": coherence["score"],
        "coherence_issues": coherence["issues"],
        "coherence_suggestion": coherence.get("suggestion", ""),
    }


async def complete_series_generation(
    draft_id: str,
    topic: str,
    goal_key: str,
    format_key: str,
    post_count: int,
    template_key: str,
) -> None:
    """Background task: generate content series and update the stub draft."""
    try:
        await set_generation_state(
            draft_id, pending=True, stage="outline",
            message="Создаю план серии...",
        )

        # RAG context
        rag_context = ""
        try:
            from bot.services.rag import retrieve_relevant_cards, format_rag_context
            cards = await retrieve_relevant_cards(topic, max_items=5)
            rag_context = format_rag_context(cards)
        except Exception:
            pass

        await set_generation_state(
            draft_id, pending=True, stage="writing",
            message="Пишу посты серии...",
        )

        loop = asyncio.get_running_loop()
        series_payload = await loop.run_in_executor(
            _executor,
            _generate_series_sync,
            topic, goal_key, format_key, post_count, template_key, rag_context,
        )

        # Finalize payload
        series_payload["generation_pending"] = False
        series_payload.pop("generation_stage", None)
        series_payload.pop("generation_message", None)
        series_payload.pop("generation_error", None)

        has_content = any(p.get("caption") for p in series_payload.get("series_posts", []))
        if not has_content:
            raise RuntimeError("Series generation produced 0 posts with content")

        await update_draft(draft_id, payload=series_payload, status="draft")

    except Exception as exc:
        logger.error("Series generation failed for %s: %s", draft_id, exc, exc_info=True)
        await set_generation_state(
            draft_id, pending=False, stage="error",
            message="Не удалось создать серию постов. Попробуйте ещё раз.",
            error=str(exc),
        )
