from __future__ import annotations

from bot.services.brand_settings_store import get_brand_settings_cached
from bot.services.claude_client import call_claude

_PLAN_PROMPT = """\
{brand_context}

Составь контент-план на неделю (7 дней, 3 публикации: пн/ср/пт).

Тренды недели для вдохновения:
{trends_text}
{social_trends_text}

Для каждого поста укажи:
- День недели
- Платформа (Threads / Instagram / Telegram / Reels)
- Формат (пост / карусель / рилс / сторис)
- Цель (Доверие / Вовлечение / Продажа / Экспертность)
- Тема поста (1-2 предложения)
- Угол (краткая идея подачи)

Правила письма: тире (— –) → запятая. Запрещено: "важно отметить", "данный", "осуществляется", "в рамках", markdown-форматирование.

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


def generate_plan_sync(trends_text: str, social_trends_text: str = "") -> str:
    bs = get_brand_settings_cached()
    prompt = _PLAN_PROMPT.format(
        brand_context=bs.brand_voice,
        trends_text=trends_text,
        social_trends_text=social_trends_text,
    )
    return call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
        context="planner",
    )
