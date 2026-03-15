"""Blend Composer — creates blend recipes from goals and available oils."""

from __future__ import annotations

import json
import logging

from config import settings
from bot.services.brand_settings_store import get_brand_settings_cached
from bot.services.blends_store import list_blends

logger = logging.getLogger(__name__)

_COMPOSE_PROMPT = """\
{brand_voice}

Ты — эксперт по составлению аромасмесей.

Цель: {goal}
Доступные масла: {oils}

Известные смеси из базы знаний:
{known_blends}

Составь аромасмесь для указанной цели. Используй только доступные масла (если список пуст, предложи \
любые подходящие). Опирайся на известные смеси, если они подходят.

ВАЖНО: Никаких медицинских обещаний. Только рекомендации по ароматерапии.

Верни строго JSON (без markdown):
{{"name": "название смеси", "ingredients": [{{"oil": "название масла", "ratio": 0.0, "unit": "капли"}}], \
"instructions": "как применять", "contraindications": "противопоказания"}}
"""


async def compose_blend(
    goal: str, oils_available: list[str] | None = None
) -> dict:
    """Compose a blend recipe for the given goal.

    Returns: {"name", "ingredients", "instructions", "contraindications"}
    """
    import anthropic

    bs = get_brand_settings_cached()
    known = await list_blends(goal=goal, limit=5)
    known_text = "\n".join(
        f"- {b.name}: {', '.join(i.get('oil_slug', '') for i in b.ingredients)}"
        for b in known
    ) or "Нет подходящих смесей в базе."

    oils_text = ", ".join(oils_available) if oils_available else "любые подходящие"

    prompt = _COMPOSE_PROMPT.format(
        brand_voice=bs.brand_voice,
        goal=goal,
        oils=oils_text,
        known_blends=known_text,
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("blend_composer: failed to parse JSON, returning raw")
        return {
            "name": goal,
            "ingredients": [],
            "instructions": raw,
            "contraindications": "",
        }
