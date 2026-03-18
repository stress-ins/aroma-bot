from __future__ import annotations

from bot.agents.content import _HUMAN_WRITING_RULES
from bot.services.claude_client import call_claude
from bot.services.brand_settings_store import get_brand_settings_cached
from bot.services.humanizer import humanize

ADAPT_PLATFORM_SPECS = {
    "instagram": "Instagram: до 900 символов, эмоциональное начало, структурированный текст с абзацами, хэштеги в конце.",
    "telegram": "Telegram: до 1200 символов, экспертный тон, можно глубже и подробнее, без лишних хэштегов.",
    "reels": "Reels/TikTok подпись: 1-2 живых предложения как крючок + 2-3 хэштега. Пост короткий, зовёт смотреть видео.",
}

ADAPT_PLATFORM_LABELS = {
    "instagram": "Instagram",
    "telegram": "Telegram",
    "reels": "Reels",
}

_ADAPT_PROMPT = """\
{brand_voice}

Адаптируй текст ниже под платформу {platform_label}.
Требования платформы: {platform_spec}

{human_writing_rules}

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
    bs = get_brand_settings_cached()
    prompt = _ADAPT_PROMPT.format(
        brand_voice=bs.brand_voice,
        platform_label=ADAPT_PLATFORM_LABELS.get(target_platform, target_platform),
        platform_spec=ADAPT_PLATFORM_SPECS.get(target_platform, ""),
        human_writing_rules=_HUMAN_WRITING_RULES,
        original_text=original_text,
    )
    text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        context="adapter",
    )
    return humanize(text, target_platform)
