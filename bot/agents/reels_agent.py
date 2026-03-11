from __future__ import annotations

from dataclasses import dataclass

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

_DIRECTOR_PROMPT = """\
Ты — режиссёр Reels. Тебе дан сценарий видео по теме: {topic}

СЦЕНАРИЙ:
{script}

Контекст бренда: регуляция нервной системы через сенсорные практики (ароматерапия, медитации, гонг).
Визуальный стиль: терракота, беж, шалфей; природные текстуры, травы, свечи, руки, мягкий свет.

Разбей видео на 4 ключевых кадра раскадровки. Для каждого кадра опиши точную сцену и дай промпт для генерации изображения.

Формат — строго (не отступай от него):

КАДР1_ТАЙМКОД: 0-3 сек
КАДР1_СЦЕНА: [что именно в кадре — предметы, детали, атмосфера]
КАДР1_РАКУРС: [ракурс камеры, движение]
КАДР1_ПРОМПТ: [English prompt for image generation, vertical portrait composition, brand aesthetic, NO faces, NO text, NO typography]

КАДР2_ТАЙМКОД: 3-10 сек
КАДР2_СЦЕНА: ...
КАДР2_РАКУРС: ...
КАДР2_ПРОМПТ: ...

КАДР3_ТАЙМКОД: 10-20 сек
КАДР3_СЦЕНА: ...
КАДР3_РАКУРС: ...
КАДР3_ПРОМПТ: ...

КАДР4_ТАЙМКОД: 20-30 сек
КАДР4_СЦЕНА: ...
КАДР4_РАКУРС: ...
КАДР4_ПРОМПТ: ...

Промпты пиши на английском. Включай: конкретные предметы сцены, цветовую палитру бренда (terracotta/beige/sage), освещение (soft natural light), настроение. Стиль: atmospheric, cinematic still, no people.
"""


@dataclass
class StoryboardFrame:
    timecode: str
    scene: str
    angle: str
    gemini_prompt: str


def _parse_storyboard(raw: str) -> list[StoryboardFrame]:
    frames: list[StoryboardFrame] = []
    for i in range(1, 5):
        timecode = scene = angle = prompt = ""
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith(f"КАДР{i}_ТАЙМКОД:"):
                timecode = line.split(":", 1)[1].strip()
            elif line.startswith(f"КАДР{i}_СЦЕНА:"):
                scene = line.split(":", 1)[1].strip()
            elif line.startswith(f"КАДР{i}_РАКУРС:"):
                angle = line.split(":", 1)[1].strip()
            elif line.startswith(f"КАДР{i}_ПРОМПТ:"):
                prompt = line.split(":", 1)[1].strip()
        if timecode or scene:
            frames.append(StoryboardFrame(
                timecode=timecode, scene=scene, angle=angle, gemini_prompt=prompt
            ))
    return frames


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


def generate_reels_director_sync(topic: str, script: str) -> list[StoryboardFrame]:
    """Director agent: breaks the script into 4 storyboard frames with Gemini prompts."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = _DIRECTOR_PROMPT.format(topic=topic, script=script)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_storyboard(resp.content[0].text.strip())
