from __future__ import annotations

import json

from config import settings


_SYSTEM_BY_CATEGORY = {
    "aroma": (
        "Ты эксперт по ароматерапии и эмоциональным картам эфирных масел. "
        "Заполняй карточку бережно, без медицинских обещаний и без псевдонаучных формулировок. "
        "Нужен практичный, ясный русский язык."
    ),
    "practice": (
        "Ты эксперт по медитации, дыхательным и телесным практикам регуляции нервной системы. "
        "Описывай безопасно, прикладно и без мистического тумана. "
        "Не обещай лечение и не выдавай практику за универсальное решение."
    ),
    "sound": (
        "Ты эксперт по sound healing, акустическим практикам и воздействию звука на состояние человека. "
        "Пиши современно, бережно и без категоричных медицинских обещаний."
    ),
}


def enrich_reference_card_sync(category: str, card: dict[str, object]) -> dict[str, object]:
    import anthropic

    if not settings.anthropic_api_key:
        return card

    system_prompt = _SYSTEM_BY_CATEGORY.get(category, _SYSTEM_BY_CATEGORY["practice"])
    payload = json.dumps(card, ensure_ascii=False, indent=2)
    user_prompt = (
        "Дополни и улучши карточку справочника. "
        "Верни строго JSON с теми же ключами, без markdown и без дополнительных пояснений.\n\n"
        f"Категория: {category}\n"
        f"Карточка:\n{payload}\n\n"
        "Требования:\n"
        "- усили поля description, questions, nps_effect, therapeutic_properties, psychological_properties, history\n"
        "- сохрани краткость и прикладной тон\n"
        "- если данных мало, аккуратно дополни экспертными формулировками общего характера\n"
        "- не убирай существующие важные факты\n"
        "- в questions дай 3-5 рефлексивных вопросов\n"
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1800,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = resp.content[0].text.strip()
    try:
        enriched = json.loads(text)
    except json.JSONDecodeError:
        return card
    return enriched if isinstance(enriched, dict) else card
