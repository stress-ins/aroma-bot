from __future__ import annotations

from config import settings

_PLATFORM_RULES = {
    "threads": (
        "Платформа: Threads. Максимум 450 символов. "
        "Одна сильная первая строка = хук. "
        "Тело — плотное, без воды. "
        "3-5 хэштегов в конце."
    ),
    "instagram": (
        "Платформа: Instagram. Максимум 900 символов. "
        "Хук + история / наблюдение + мягкий CTA. "
        "3-7 хэштегов в конце."
    ),
    "telegram": (
        "Платформа: Telegram. Максимум 1200 символов. "
        "Чуть глубже, чем в соцсетях, но компактно. "
        "Без хэштегов."
    ),
    "default": "Короткий пост для соцсетей. Сохрани длину оригинала.",
}

_EDITOR_SYSTEM = """\
Ты — главред с 10-летним опытом редактуры контента для Instagram и Threads \
в нишах wellbeing, психология, образ жизни.

Правила редактуры:
1. Первая строка — останавливает скролл. Провокация, факт, признание, вопрос без \
   ответа. Плохо: "В нашей работе есть важная деталь." \
   Хорошо: "Большинство корпоративных велнес-программ — это красивая бумажка."
2. Убери AI-штампы: "погружаясь в...", "исследуя...", "это то, что...", \
   "позволь себе...", "мощный инструмент", "невероятный результат".
3. Убери длинные вводные. Первое слово — сразу в суть.
4. Тело: телесные образы и узнаваемые жизненные ситуации вместо абстракций.
5. CTA — человеческий, не рекламный. Как будто пишешь другу.
6. Не увеличивай длину. Лучше сократи.
7. Верни только отредактированный текст поста — ничего больше.
"""


def edit_post_sync(raw: str, topic: str, platform: str = "default") -> str:
    """Run an editor pass over a raw post. Returns the polished post text."""
    import anthropic

    platform_rule = _PLATFORM_RULES.get(platform, _PLATFORM_RULES["default"])
    user_msg = (
        f"Тема поста: {topic}\n"
        f"{platform_rule}\n\n"
        f"Черновик:\n{raw}"
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
        system=_EDITOR_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    result = resp.content[0].text.strip()
    # Fallback: if editor returns something too short, keep original
    return result if len(result) > 30 else raw
