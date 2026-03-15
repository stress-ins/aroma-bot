from __future__ import annotations

from config import settings
from bot.services.brand_settings_store import get_brand_settings_cached

ADAPT_PLATFORM_SPECS = {
    "threads": "Threads: 3 поста на сегодня в порядке Утро / День / Вечер. Каждый пост с одной идеей, 5-12 коротких строк, 40-120 слов, разговорный стиль, без хэштегов.",
    "instagram": "Instagram: до 900 символов, эмоциональное начало, структурированный текст с абзацами, хэштеги в конце.",
    "telegram": "Telegram: до 1200 символов, экспертный тон, можно глубже и подробнее, без лишних хэштегов.",
    "reels": "Reels/TikTok подпись: 1-2 живых предложения как крючок + 2-3 хэштега. Пост короткий, зовёт смотреть видео.",
}

ADAPT_PLATFORM_LABELS = {
    "threads": "Threads",
    "instagram": "Instagram",
    "telegram": "Telegram",
    "reels": "Reels",
}

_ADAPT_PROMPT = """\
{brand_voice}

Адаптируй текст ниже под платформу {platform_label}.
Требования платформы: {platform_spec}

Общие правила:
- Сохраняй суть и ключевой месседж оригинала.
- Подстраивай длину, тон и структуру под платформу.
- Пиши по-русски, от первого лица.
- Не добавляй информацию, которой нет в оригинале.

Оригинальный текст:
{original_text}

Верни только адаптированный текст — ничего больше.
"""


def adapt_text_sync(original_text: str, target_platform: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    bs = get_brand_settings_cached()
    prompt = _ADAPT_PROMPT.format(
        brand_voice=bs.brand_voice,
        platform_label=ADAPT_PLATFORM_LABELS.get(target_platform, target_platform),
        platform_spec=ADAPT_PLATFORM_SPECS.get(target_platform, ""),
        original_text=original_text,
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
