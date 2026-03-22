from __future__ import annotations

from config import settings
from bot.services.claude_client import call_claude

TONE_CONFIGS = {
    "official": {
        "instruction": (
            "Пиши официально и профессионально. Стиль — эксперт в ароматерапии. "
            "Структурированно, без лишних эмоций. До 300 символов."
        ),
        "max_length": 300,
    },
    "warm": {
        "instruction": (
            "Пиши тепло, как хороший знакомый. Искренне, с заботой. "
            "Можно задать вопрос в ответ. До 200 символов."
        ),
        "max_length": 200,
    },
    "provocative": {
        "instruction": (
            "Пиши остро, неожиданно, немного провоцируй мышление. "
            "Короткий мощный ответ. До 120 символов."
        ),
        "max_length": 120,
    },
}


def generate_replies_sync(
    content: str,
    author_username: str,
    platform: str,
    context_post: str = "",
) -> list[dict]:
    """Generate 3 reply variants (official, warm, provocative) via Claude sync client.

    Returns list of dicts: [{tone, content}, ...]
    """
    if not settings.anthropic_api_key:
        return []

    context_block = f"\nКонтекст поста: {context_post}" if context_post else ""
    platform_hint = {
        "threads": "Threads (аудитория — интересующиеся благополучием, ароматерапией)",
        "instagram": "Instagram (визуальная платформа, подписчики следят за контентом)",
        "telegram": "Telegram (более приватная среда, подписчики канала)",
        "youtube": "YouTube (комментарии под видео, аудитория шире, тон может быть развёрнутым)",
    }.get(platform, platform)

    replies = []

    for tone, cfg in TONE_CONFIGS.items():
        prompt = f"""\
Ты — эксперт-редактор в области ароматерапии. Пишешь от имени автора блога об ароматерапии.

Платформа: {platform_hint}
Автор упоминания: @{author_username}
Их сообщение: {content}{context_block}

Задача: написать один ответ в тоне "{tone}".
Инструкция по тону: {cfg["instruction"]}

Правила:
- Не обещай лечение, не давай медицинских рекомендаций
- Отвечай по-русски
- Только сам текст ответа, без пояснений
"""
        try:
            text = call_claude(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                context="mentions_agent",
            )
            # Trim to max_length
            if len(text) > cfg["max_length"]:
                text = text[: cfg["max_length"]].rsplit(" ", 1)[0]
            replies.append({"tone": tone, "content": text})
        except Exception:
            replies.append({"tone": tone, "content": ""})

    return replies
