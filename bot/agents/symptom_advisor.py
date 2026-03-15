"""Symptom Advisor — recommends oils and blends for symptoms."""

from __future__ import annotations

import json
import logging

from config import settings
from bot.services.brand_settings_store import get_brand_settings_cached
from bot.services.blends_store import list_blends

logger = logging.getLogger(__name__)

_ADVISE_PROMPT = """\
{brand_voice}

Ты — эксперт по ароматерапии.

Симптом или состояние: {symptom}

Известные смеси из базы знаний:
{known_blends}

Предложи масла и/или смеси, которые могут помочь при данном состоянии.

ВАЖНО: Никаких медицинских обещаний. Только рекомендации по ароматерапии. \
Обязательно указывай противопоказания.

Верни строго JSON массив (без markdown):
[{{"oil_or_blend": "название", "type": "oil" или "blend", "reason": "почему подходит", \
"contraindications": "противопоказания"}}]
"""


async def advise_by_symptom(symptom: str) -> list[dict]:
    """Recommend oils/blends for a symptom.

    Returns: [{"oil_or_blend", "type", "reason", "contraindications"}]
    """
    import anthropic

    bs = get_brand_settings_cached()
    known = await list_blends(limit=20)
    known_text = "\n".join(
        f"- {b.name} (цель: {b.goal}): {b.indications[:100]}"
        for b in known
        if b.indications
    ) or "Нет данных о смесях."

    prompt = _ADVISE_PROMPT.format(
        brand_voice=bs.brand_voice,
        symptom=symptom,
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
        result = json.loads(raw)
        return result if isinstance(result, list) else [result]
    except json.JSONDecodeError:
        logger.warning("symptom_advisor: failed to parse JSON")
        return [{"oil_or_blend": symptom, "type": "oil", "reason": raw, "contraindications": ""}]
