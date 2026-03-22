"""Series Writer agent: generates posts for a content series in batches."""

from __future__ import annotations

import logging
import re

from bot.services.humanizer import humanize

logger = logging.getLogger(__name__)


def generate_posts_batch_sync(
    topic: str,
    goal_key: str,
    format_key: str,
    outline_text: str,
    positions: list[dict],
    previous_summaries: str,
    goal_guidance: dict[str, str],
    rag_context: str = "",
) -> list[dict]:
    """Generate a batch of posts for the series.

    Returns list of dicts: [{index, caption, cta, visual_prompt, hashtags}].
    """
    from bot.agents.prompts.series_prompts import writer_batch_prompt
    from bot.services.claude_client import call_claude

    format_labels = {
        "threads_series": "Серия Threads",
        "instagram": "Instagram",
        "telegram": "Telegram",
        "carousel": "Карусель",
    }

    prompt = writer_batch_prompt(
        topic, goal_key, format_key, outline_text, positions,
        previous_summaries, goal_guidance, rag_context=rag_context,
    )

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
        context="series_writer",
    )

    return _parse_posts_batch(raw, positions)


def _parse_posts_batch(raw: str, positions: list[dict]) -> list[dict]:
    """Parse batch of posts from Claude response."""
    posts = []
    current_post = None
    current_field = ""

    for line in raw.strip().splitlines():
        line = line.strip()

        # ===POST N===
        m = re.match(r"={2,}POST\s+(\d+)={2,}", line, re.IGNORECASE)
        if m:
            if current_post is not None:
                posts.append(current_post)
            idx = int(m.group(1)) - 1
            current_post = {
                "index": idx,
                "caption": "",
                "cta": "",
                "visual_prompt": "",
                "hashtags": "",
            }
            current_field = ""
            continue

        if current_post is None:
            continue

        cleaned = line.replace("**", "").strip()
        if cleaned.upper().startswith("CAPTION:"):
            current_post["caption"] = humanize(cleaned.split(":", 1)[1].strip())
            current_field = "caption"
        elif cleaned.upper().startswith("CTA:"):
            current_post["cta"] = humanize(cleaned.split(":", 1)[1].strip())
            current_field = "cta"
        elif cleaned.upper().startswith("VISUAL_PROMPT:"):
            current_post["visual_prompt"] = cleaned.split(":", 1)[1].strip()
            current_field = "visual_prompt"
        elif cleaned.upper().startswith("HASHTAGS:"):
            current_post["hashtags"] = cleaned.split(":", 1)[1].strip()
            current_field = "hashtags"
        elif current_field == "caption" and line:
            current_post["caption"] += "\n" + humanize(line)

    if current_post is not None:
        posts.append(current_post)

    # Map posts to expected positions
    result = []
    posts_by_idx = {p["index"]: p for p in posts}

    for pos in positions:
        idx = pos["index"]
        if idx in posts_by_idx:
            p = posts_by_idx[idx]
            result.append(p)
        else:
            # Fallback: empty post
            result.append({
                "index": idx,
                "caption": "",
                "cta": "",
                "visual_prompt": "",
                "hashtags": "",
            })

    return result


def summarize_posts(posts: list[dict]) -> str:
    """Create brief summaries of posts for context threading."""
    lines = []
    for p in posts:
        idx = p.get("index", 0) + 1
        caption = (p.get("caption") or "")[:120]
        if caption:
            lines.append(f"Пост {idx}: {caption}...")
    return "\n".join(lines)
