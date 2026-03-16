"""Compatibility Checker — checks oil combinations for safety."""

from __future__ import annotations

import json
import logging

from bot.services.brand_settings_store import get_brand_settings_cached
from bot.services.claude_client import call_claude
from bot.services.blends_store import search_by_ingredient

logger = logging.getLogger(__name__)

_CHECK_PROMPT = """\
{brand_voice}

Ты — эксперт по безопасности ароматерапии.

Масла для проверки совместимости: {oils}

Известные комбинации из базы знаний:
{known_combos}

Проверь совместимость этих масел. Укажи:
1. Совместимы ли они друг с другом
2. Предупреждения (аллергия, фототоксичность и т.д.)
3. Противопоказания
4. Синергии (масла, которые усиливают друг друга)

ВАЖНО: Никаких медицинских обещаний. Только рекомендации по ароматерапии.

Верни строго JSON (без markdown):
{{"compatible": true/false, "warnings": ["предупреждение"], \
"contraindications": ["противопоказание"], "synergies": ["синергия"]}}
"""


async def check_compatibility(oils: list[str]) -> dict:
    """Check compatibility of a list of oils.

    Returns: {"compatible", "warnings", "contraindications", "synergies"}
    """
    bs = get_brand_settings_cached()

    # Find known blends containing these oils
    combos: list[str] = []
    for oil in oils[:5]:  # limit lookups
        blends = await search_by_ingredient(oil)
        for b in blends:
            combos.append(f"- {b.name}: {', '.join(i.get('oil_slug', '') for i in b.ingredients)}")
    known_text = "\n".join(set(combos)) or "Нет данных о комбинациях."

    prompt = _CHECK_PROMPT.format(
        brand_voice=bs.brand_voice,
        oils=", ".join(oils),
        known_combos=known_text,
    )

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        context="compatibility_checker",
    )

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("compatibility_checker: failed to parse JSON")
        return {
            "compatible": True,
            "warnings": [],
            "contraindications": [],
            "synergies": [],
        }
