from __future__ import annotations

from config import settings

_BRAND_CONTEXT = """\
Ты — сценарист Reels для специалиста по регуляции нервной системы через сенсорные практики \
(ароматерапия, медитации, гонг).

Голос: спокойный, живой, экспертный. Без инфоцыганства и псевдомедицинских обещаний.
Визуальный стиль: терракота, беж, шалфей; природные текстуры, травы, свечи, руки, мягкий свет.\
"""

_TOPICS_PROMPT = """\
{brand_context}

Предложи 7 тем для Reels (15-30 сек).

Тренды для вдохновения:
{trends_text}

Требования к темам:
- Зацепка в первые 3 секунды (визуальная или вербальная)
- Один конкретный инсайт или мини-практика
- Подходит для съёмки в домашних/студийных условиях

Верни строго нумерованный список без пояснений:
1. ...
7. ...
"""

_SCENARIO_PROMPT = """\
{brand_context}

Напиши детальный сценарий Reels (15-30 сек) по теме: {topic}

Структура:
ХРОНОМЕТРАЖ: 0-3 сек | Хук
- Видеоряд: [что снимать]
- Текст на экране: [текст]
- Закадровый голос: [что говорить]

ХРОНОМЕТРАЖ: 3-10 сек | Основная часть
- Видеоряд: ...
- Текст на экране: ...
- Закадровый голос: ...

ХРОНОМЕТРАЖ: 10-20 сек | Развитие / практика
- Видеоряд: ...
- Текст на экране: ...
- Закадровый голос: ...

ХРОНОМЕТРАЖ: 20-30 сек | CTA
- Видеоряд: ...
- Текст на экране: ...
- Закадровый голос: ...

ОПИСАНИЕ ДЛЯ ПОСТА: [2-3 предложения + хэштеги]
МУЗЫКАЛЬНОЕ НАСТРОЕНИЕ: [описание трека — темп, инструменты, атмосфера]
"""


def generate_reels_topics_sync(trends_text: str) -> list[str]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = _TOPICS_PROMPT.format(brand_context=_BRAND_CONTEXT, trends_text=trends_text)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    topics: list[str] = []
    for line in resp.content[0].text.strip().splitlines():
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            topics.append(line.split(". ", 1)[1].strip())
    return topics[:7]


def generate_reels_scenario_sync(topic: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = _SCENARIO_PROMPT.format(brand_context=_BRAND_CONTEXT, topic=topic)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
