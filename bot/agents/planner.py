from __future__ import annotations

from config import settings

_BRAND_CONTEXT = """\
Ты — контент-стратег специалиста по регуляции нервной системы через сенсорные практики \
(ароматерапия, медитации, гонг).

Аудитория: люди с перегрузкой и стрессом + компании для wellbeing-программ.
Голос: спокойный, ясный, экспертный. Без инфоцыганства и псевдомедицинских обещаний.
Цели контента: доверие, вовлечение, продажи, демонстрация экспертности.\
"""

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
    prompt = _PLAN_PROMPT.format(brand_context=_BRAND_CONTEXT, trends_text=trends_text)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
