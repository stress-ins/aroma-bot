from __future__ import annotations

from config import settings

_EDITOR_PROMPT = """\
Ты — главред контента для Instagram с 10-летним опытом в нише wellbeing и психологии.

Автор: эксперт по регуляции нервной системы через сенсорные практики (ароматерапия, \
медитации, гонг). Форматы: личные сессии, групповые практики, корпоративный wellbeing.
Цель карусели: человек дочитывает и думает «хочу попробовать» — пишет в ДМ или сохраняет.

Структура 6 слайдов:
SLIDE1 — Hook: первая строка останавливает скролл. Факт, провокация или \
  узнаваемая ситуация. Не вопрос «А вы знали, что...».
SLIDE2 — Проблема: конкретная ситуация из жизни, не абстракция. «Голова не \
  отключается после 22:00» — да. «Стресс мешает нам жить» — нет.
SLIDE3 — Механизм: почему так происходит — просто, телесно, без науки и \
  без «парасимпатика активируется».
SLIDE4 — Инсайт: момент «ага». Переключение угла зрения. Не вывод, а открытие.
SLIDE5 — Решение: конкретная практика или шаг. Без обещаний «изменит всё».
SLIDE6 — CTA: человеческое приглашение, не рекламная фраза. «Если интересно \
  попробовать — напиши в ДМ» — да. «Записывайся прямо сейчас!» — нет.

Критические правила:
- Максимум 5-6 строк на слайд, каждая строка ≤ 10 слов
- 1 мысль = 1 строка. Разговорный, живой язык
- Убери AI-штампы: «погружаясь в», «исследуя», «позволь себе», «мощный инструмент»
- Убери длинные тире — замени на запятую, точку или перенос строки
- Не увеличивай текст — лучше сократи
- Тон: спокойный, экспертный, современный. Без эзотерики, пафоса, инфоцыганства

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


def edit_carousel_sync(raw_slides: list[str], topic: str) -> list[str]:
    import anthropic

    raw_text = "\n".join(f"Слайд {i + 1}: {s}" for i, s in enumerate(raw_slides))
    prompt = _EDITOR_PROMPT.format(topic=topic, raw_slides=raw_text)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()

    slides: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        for i in range(1, 7):
            if line.startswith(f"SLIDE{i}:"):
                slides.append(line.split(":", 1)[1].strip())
                break

    # Fallback: return originals if parsing failed
    return slides[:6] if len(slides) >= 4 else raw_slides
