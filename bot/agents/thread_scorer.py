"""Score Threads posts for brand relevance and extract content angles."""
from __future__ import annotations

import json
import logging

from bot.agents.platform_rules import get_brand_context
from bot.services.claude_client import call_claude

logger = logging.getLogger(__name__)


def _extract_json_array(raw: str) -> list[dict]:
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []


def score_threads_batch_sync(candidates: list[dict]) -> list[dict]:
    """Score up to 20 Threads candidates for brand relevance."""
    if not candidates:
        return []

    brand_ctx = get_brand_context()
    numbered = []
    for i, post in enumerate(candidates[:20]):
        numbered.append(
            f"[{i}] @{post.get('author', post.get('username', ''))} "
            f"(source={post.get('source', '?')}, "
            f"likes={post.get('like_count', 0)}): "
            f"{post.get('text', '')[:400]}"
        )

    prompt = f"""\
{brand_ctx}

Ты — контент-стратег. Оцени посты из Threads на релевантность для бренда.

Бренд занимается: ароматерапией, гонг-медитацией, сенсорным велнесом, регуляцией нервной системы.
Аудитория: люди, интересующиеся осознанностью, восстановлением, природными практиками.

Посты:
{chr(10).join(numbered)}

Для каждого поста верни JSON:
{{
  "index": 0,
  "relevance_score": 0.0-1.0,
  "ai_summary": "одна строка — о чём пост",
  "content_angle": "конкретная тема для нашего поста или '' если не релевантно",
  "suggested_action": "reply|create_content|engage|dismiss",
  "topic_tags": ["тег1", "тег2"]
}}

Оценивай строго: score >= 0.7 только если явная связь с нашей темой.
0.5-0.7 — косвенная связь. < 0.5 — не релевантно.

Верни JSON-массив.
"""

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        context="thread_scorer",
    )

    scored = _extract_json_array(raw)
    score_map = {item["index"]: item for item in scored if "index" in item}

    result = []
    for i, post in enumerate(candidates[:20]):
        meta = score_map.get(i, {})
        result.append({
            **post,
            "relevance_score": float(meta.get("relevance_score", 0.0)),
            "ai_summary": str(meta.get("ai_summary", "")),
            "content_angle": str(meta.get("content_angle", "")),
            "suggested_action": str(meta.get("suggested_action", "dismiss")),
            "topic_tags": list(meta.get("topic_tags", [])),
        })
    for post in candidates[20:]:
        result.append(post)
    return result
