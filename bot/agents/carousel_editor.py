from __future__ import annotations

import re

from config import settings

_DEFAULT_FORBIDDEN_PHRASES = [
    "голова не отключается",
    "кажется, что ничего не помогает",
    "твоему телу нужен сигнал",
    "запах это первое что замечает нервную систему",
    "у каждого свой аромат",
    "земляная база",
    "в ДМ",
]

_SOFT_REWRITES: tuple[tuple[str, str], ...] = (
    (r"\bв\s*дм\b", "в личные сообщения"),
    (r"земляная база", "ощущение опоры под ногами"),
    (r"твоему телу нужен сигнал", "телу важно почувствовать, что можно выдохнуть"),
    (r"запах это первое что замечает нервную систему", "аромат тело замечает почти сразу"),
    (r"кажется,\s*что ничего не помогает", "ты уже многое пробовала, а напряжение все равно держится"),
)

_EDITOR_PROMPT = """\
Ты — главред контента для Instagram с 10-летним опытом в нише wellbeing и психологии.

Автор: эксперт по регуляции нервной системы через сенсорные практики (ароматерапия, \
медитации, гонг). Форматы: личные сессии, групповые практики, корпоративный wellbeing.
Цель карусели: человек дочитывает и думает «хочу попробовать» — пишет в ДМ или сохраняет.

Структура 6 слайдов:
SLIDE1 — Hook: первая строка останавливает скролл. Факт, провокация или \
  узнаваемая ситуация. Не вопрос «А вы знали, что...».
SLIDE2 — Проблема: конкретная ситуация из жизни, не абстракция. «Голова не \
  крутится до ночи» — да. «Стресс мешает нам жить» — нет.
SLIDE3 — Механизм: почему так происходит — просто, телесно, без науки и \
  без «парасимпатика активируется».
SLIDE4 — Инсайт: момент «ага». Переключение угла зрения. Не вывод, а открытие.
SLIDE5 — Решение: конкретная практика или шаг. Без обещаний «изменит всё».
SLIDE6 — CTA: человеческое приглашение, не рекламная фраза. CTA может быть разным, \
  но должен звучать по-русски и по-человечески. «Если хочешь попробовать, напиши», \
  «Если откликается, расскажу подробнее» — да. «Записывайся прямо сейчас!» — нет.

Критические правила:
- Максимум 5-6 строк на слайд, каждая строка ≤ 10 слов
- 1 мысль = 1 строка. Разговорный, живой язык — как говорит умная подруга, не как лектор
- Каждый следующий слайд должен логично продолжать предыдущий. Человек должен читать и чувствовать, что его спокойно ведут дальше, а не кидают из мысли в мысль.
- Пиши мягко, понятно и по-человечески. Без жёстких формулировок, без "умничающего" тона, без ощущения, что текст старается звучать глубоко любой ценой.
- Лучше простая и ясная фраза, чем красивая, но странная. Если строка звучит неестественно в обычной речи, перепиши проще.
- Убери AI-штампы: «погружаясь в», «исследуя», «позволь себе», «мощный инструмент»
- Убери умные термины там, где можно сказать проще. \
  Плохо: «активация парасимпатики», «интеграция опыта», «ресурсное состояние». \
  Хорошо: «стало чуть легче», «голова не отключается», «не можешь уснуть»
- Никаких литературных метафор. Конкретность = слова из живого разговора, не из книги. \
  Плохо: «плечи в камне», «душа не отпускает», «тело как свинец». \
  Хорошо: «плечи не расслабляются», «не можешь уснуть», «голова не отключается»
- Не используй жёсткие, странные или неуклюжие фразы. \
  Плохо: "запах попадает быстрее мыслей", "нервная система не спорит", "аромат вскрывает женскую природу". \
  Хорошо: "запах срабатывает очень быстро", "тело замечает аромат почти сразу", "аромат помогает немного расслабиться и вернуть мягкость"
- Если описываешь проблему, уточняй, что именно не сработало. Не пиши размыто: «ничего не помогает». Покажи 1-2 конкретные попытки или симптома.
- Если пишешь про тело, избегай туманных слов вроде «сигнал», если не объясняешь, какой именно. Лучше сразу назвать ощущение или реакцию тела.
- Фразы вроде «у каждого свой аромат» или «земляная база» звучат незаконченно или искусственно. Пиши яснее: что именно дает аромат и в каком состоянии.
- В CTA не используй «ДМ». Пиши по-русски и естественно для автора: «напиши», «в личные сообщения», «расскажу подробнее».
- Убери длинные тире — замени на запятую, точку или перенос строки
- Не увеличивай текст — лучше сократи
- Тон: спокойный, тёплый, живой. Без эзотерики, пафоса, инфоцыганства
- Слайды должны быть приятными на слух. Не руби фразы ради эффекта, не делай текст нарочито "инстаграмным".
- Ориентир по тону: понятно, мягко, логично, как в хорошем объяснении от живого человека.
- Не используй эти фразы и их близкие варианты:
{forbidden_phrases}

Тема карусели: {topic}

Черновик слайдов:
{raw_slides}

Верни строго в формате (ничего кроме этого):
SLIDE1: [текст]
SLIDE2: [текст]
SLIDE3: [текст]
SLIDE4: [текст]
SLIDE5: [текст]
SLIDE6: [текст]
"""


def _forbidden_phrases() -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for phrase in [*_DEFAULT_FORBIDDEN_PHRASES, *getattr(settings, "carousel_forbidden_phrases_list", [])]:
        value = str(phrase).strip()
        lowered = value.lower()
        if not value or lowered in seen:
            continue
        seen.add(lowered)
        result.append(value)
    return result


def _render_forbidden_phrases_block() -> str:
    return "\n".join(f"- {item}" for item in _forbidden_phrases())


def _build_editor_prompt(topic: str, raw_slides: str) -> str:
    return _EDITOR_PROMPT.format(
        topic=topic,
        raw_slides=raw_slides,
        forbidden_phrases=_render_forbidden_phrases_block(),
    )


def _sanitize_slide_text(text: str) -> str:
    updated = text
    for pattern, replacement in _SOFT_REWRITES:
        updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
    return updated.strip()


def edit_carousel_sync(raw_slides: list[str], topic: str) -> list[str]:
    import anthropic

    raw_text = "\n".join(f"Слайд {i + 1}: {s}" for i, s in enumerate(raw_slides))
    prompt = _build_editor_prompt(topic=topic, raw_slides=raw_text)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()

    slides = [_sanitize_slide_text(item) for item in _parse_slides(text, count=6)]

    # Fallback: return originals if parsing failed
    return slides[:6] if len(slides) >= 4 else raw_slides


def _normalize_line(line: str) -> str:
    """Strip markdown bold/italic and leading punctuation from a line."""
    s = line.strip()
    # Remove **...** and __...__ wrappers at the start
    for marker in ("**", "__", "*", "_"):
        if s.startswith(marker):
            s = s[len(marker):]
    return s


def _parse_slides(text: str, count: int = 6) -> list[str]:
    """Parse SLIDE1: ... SLIDE{count}: blocks, handling multi-line content
    and common Claude formatting variations (bold markers, spaces in numbers)."""
    import re
    slots: dict[int, list[str]] = {}
    current: int | None = None

    for line in text.splitlines():
        stripped = _normalize_line(line)
        matched = False
        for i in range(1, count + 1):
            # Match SLIDE1: or SLIDE 1: (with optional space)
            prefix = f"SLIDE{i}:"
            prefix_spaced = f"SLIDE {i}:"
            if stripped.upper().startswith(prefix.upper()) or \
               stripped.upper().startswith(prefix_spaced.upper()):
                current = i
                slots[i] = []
                plen = len(prefix_spaced) if stripped.upper().startswith(prefix_spaced.upper()) else len(prefix)
                after = stripped[plen:].strip().lstrip("*_").rstrip("*_").strip()
                if after:
                    slots[i].append(after)
                matched = True
                break
        if not matched and current is not None:
            # Stop accumulating at IMG_PROMPT or empty separator between slides
            if stripped.upper().startswith("IMG_PROMPT"):
                current = None
            elif stripped:
                slots[current].append(stripped)

    result = []
    for i in range(1, count + 1):
        if i in slots:
            result.append(" ".join(slots[i]))
    return result
