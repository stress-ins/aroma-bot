from __future__ import annotations

from config import settings
from bot.services.brand_settings_store import get_brand_settings_cached

_PLAN_PROMPT = """\
{brand_context}

Составь контент-план на неделю (7 дней, 3 публикации: пн/ср/пт).

Тренды недели для вдохновения:
{trends_text}

Для каждого поста укажи:
- День недели
- Платформа (Threads / Instagram / Telegram / Reels)
- Формат (пост / карусель / рилс / сторис)
- Цель (Доверие / Вовлечение / Продажа / Экспертность)
- Тема поста (1-2 предложения)
- Угол (краткая идея подачи)

Верни строго в формате:

📅 Понедельник
Платформа: ...
Формат: ...
Цель: ...
Тема: ...
Угол: ...

📅 Среда
Платформа: ...
...

📅 Пятница
Платформа: ...
...
"""


def generate_plan_sync(trends_text: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    bs = get_brand_settings_cached()
    prompt = _PLAN_PROMPT.format(brand_context=bs.brand_voice, trends_text=trends_text)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
