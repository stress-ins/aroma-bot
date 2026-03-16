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

_INCOMPAT_PROMPT = """\
Задача смеси: {brief}
Эффекты: {effects}

Перечисли масла которые НЕЛЬЗЯ добавить в эту смесь и почему.
Только реальные несовместимости — противоположные эффекты, химические конфликты.

Верни строго в формате JSON:
[
  {{"name_ru": "Лаванда", "reason": "расслабляет, противоречит цели концентрации"}},
  {{"name_ru": "Иланг-иланг", "reason": "седативный, снижает фокус"}}
]

Максимум 5 масел. Только конкретные причины.
"""


def get_incompatible_oils_sync(effects: list[str], brief: str) -> list[dict]:
    """Synchronous check for oils incompatible with the blend goal."""
    prompt = _INCOMPAT_PROMPT.format(
        brief=brief,
        effects=", ".join(effects) if effects else "общее применение",
    )

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        model="claude-haiku-4-5-20251001",
        context="blend_constructor/compatibility",
    )

    try:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        return json.loads(raw.strip())
    except Exception:
        logger.warning("get_incompatible_oils_sync: failed to parse response")
        return []


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
