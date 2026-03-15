from __future__ import annotations

import logging
from dataclasses import dataclass

from config import settings
from bot.services.brand_settings_store import get_brand_settings_cached

logger = logging.getLogger(__name__)

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
{reference_context_block}
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

---
ОБЯЗАТЕЛЬНЫЕ ОГРАНИЧЕНИЯ:

Видеоряд — каждый кадр описывается конкретно: предмет + действие + план камеры.
Плохо: "она открывает флакон". Хорошо: "средний план — рука держит тёмный флакон, большой палец откручивает крышку".
НЕ использовать: дымящийся ладан, бахур, горящие ароматические смолы — у автора нет этого оборудования.
ГЛАВНОЕ ПРАВИЛО: тема видео — это «{topic}». Визуальный ряд ОБЯЗАН строиться вокруг этой темы.
- Если тема НЕ связана с ароматерапией/маслами (например: кабриолет, море, путешествие, спорт, кофе и т.д.) — \
снимай ИМЕННО это. Масло может появиться максимум в одном кадре как параллель или инструмент, но НЕ как главный герой.
- Если тема связана с ароматерапией или эфирными маслами — тогда:
  - НЕ показывать капли масла в воде или миске — эфирное масло в воде не растворяется.
  - Масло применяется: каплю на ладонь → растереть → вдыхать с ладоней. Или диффузор. Именно так и снимать.

Закадровый голос — разговорный язык, как подруга рассказывает подруге в голосовом сообщении.
НЕ писать следующие фразы и их близкие варианты:
{forbidden_phrases}
Вместо "мы сжимаем живот, поясницу, таз" → "у нас часто бывает напряжено тело, особенно в животе и пояснице".
Вместо "просто стой" → "просто дыши" или "просто наблюдай".
Конкретный смысл: что именно происходит с телом или состоянием, без поэтических метафор.
Плохо: "пробуждает чувственность, не подменяя её сексуальностью".
Хорошо: "помогает немного расслабиться и перестать контролировать каждый вдох".
Каждая фраза должна быть логически завершена — никаких оборванных мыслей и неполных предложений.

Текст на экране — короткие, понятные без объяснений фразы.
Каждая строка текста на экране должна быть самостоятельной законченной мыслью.
Плохо: "раскрыть женское" — обрывается, непонятно. Хорошо: "расслабиться и почувствовать себя живой".
Для свойств аромата писать: устойчивость, уверенность, мягкость, принятие, опора — НЕ "укоренённость".
"""

_DIRECTOR_PROMPT = """\
Ты — режиссёр Reels. Тебе дан сценарий видео по теме: {topic}

СЦЕНАРИЙ:
{script}

Контекст бренда: регуляция нервной системы через сенсорные практики (ароматерапия, медитации, гонг).
Визуальный стиль: терракота, беж, шалфей; природные текстуры, травы, свечи, руки, мягкий свет.

Разбей видео на 4 ключевых кадра раскадровки. Для каждого кадра опиши точную сцену и дай промпт для генерации изображения.

Требования к КАДР_СЦЕНА:
- Обязательно: что за предмет в кадре + что происходит + какой план (макро/средний/общий)
- Хорошо: "макро — горлышко тёмного стеклянного флакона, пальцы откручивают крышку, мягкий боковой свет"
- Плохо: "она открывает флакон" — непонятно что именно снимать
- НЕ использовать: дымящийся ладан, горящие смолы
- ГЛАВНОЕ: снимай то, что соответствует теме видео «{topic}». \
Если тема НЕ про ароматерапию — масло может появиться максимум в одном кадре, остальные кадры — по теме.
- Если тема про ароматерапию/масла: НЕ капли в воду; масло — каплю на ладонь → растереть → вдыхать. Именно так снимать.

Формат — строго (не отступай от него):

КАДР1_ТАЙМКОД: 0-3 сек
КАДР1_СЦЕНА: [что именно в кадре — предмет, детали, атмосфера]
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

_REFERENCE_CONTEXT_MAX_CHARS = 1800


@dataclass
class StoryboardFrame:
    timecode: str
    scene: str
    angle: str
    gemini_prompt: str


def _parse_storyboard(raw: str) -> list[StoryboardFrame]:
    normalized_lines: list[str] = []
    for line in raw.splitlines():
        probe = line.strip()
        probe = probe.removeprefix("- ").strip()
        probe = probe.replace("**", "").replace("__", "").strip()
        normalized_lines.append(probe)

    frames: list[StoryboardFrame] = []
    for i in range(1, 5):
        timecode = scene = angle = prompt = ""
        for line in normalized_lines:
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
    bs = get_brand_settings_cached()
    prompt = _TOPICS_PROMPT.format(brand_context=bs.brand_voice, trends_text=trends_text)
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


def _render_reference_context_block(reference_context: str) -> str:
    text = str(reference_context or "").strip()
    if not text:
        return ""
    bounded = text[:_REFERENCE_CONTEXT_MAX_CHARS].rstrip()
    return (
        "\nДанные из нашего справочника (используй для точности описаний и формулировок):\n"
        + bounded
        + "\n"
    )


def generate_reels_scenario_sync(topic: str, reference_context: str = "") -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    bs = get_brand_settings_cached()
    forbidden_block = "\n".join(f"- {p}" for p in bs.forbidden_phrases) if bs.forbidden_phrases else ""
    prompt = _SCENARIO_PROMPT.format(
        brand_context=bs.brand_voice,
        reference_context_block=_render_reference_context_block(reference_context),
        topic=topic,
        forbidden_phrases=forbidden_block,
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1600,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def generate_reels_director_sync(topic: str, script: str) -> list[StoryboardFrame]:
    """Director agent: breaks the script into 4 storyboard frames with Gemini prompts."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = _DIRECTOR_PROMPT.format(topic=topic, script=script)
    last_raw = ""

    for attempt in range(2):
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1400,
            messages=[{"role": "user", "content": prompt}],
        )
        last_raw = resp.content[0].text.strip()
        frames = _parse_storyboard(last_raw)
        if len(frames) >= 4:
            return frames[:4]
        logger.warning("Reels director parse returned %d frames on attempt %d", len(frames), attempt + 1)

    logger.warning("Reels director fallback: returning %d parsed frames", len(frames))
    if last_raw:
        logger.warning("Reels director raw response preview: %s", last_raw[:800])
    return frames[:4]
