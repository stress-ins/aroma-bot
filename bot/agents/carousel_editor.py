from __future__ import annotations

from config import settings

_EDITOR_PROMPT = """\
Ты — редактор короткого контента для Instagram с опытом работы с экспертами \
в нише wellbeing и психологии.

Твоя задача — переработать черновик карусели, сделав его максимально читаемым \
и сильным для Instagram.

Контекст автора:
Эксперт работает с регуляцией нервной системы через сенсорные практики:
— ароматерапия, медитации, гонг
Форматы: личные сессии, практики для групп, корпоративные wellbeing-мероприятия.
Цель карусели: привести человека к мысли написать в ДМ или записаться на практику.

Структура 6 слайдов:
SLIDE1 — Hook: цепляющий хук, заставляет свайпнуть
SLIDE2 — Relatable проблема: узнаваемая ситуация из жизни
SLIDE3 — Объяснение механизма: почему так происходит (просто, без науки)
SLIDE4 — Осознание / инсайт: момент «ага», переключение восприятия
SLIDE5 — Решение: конкретная практика или подход
SLIDE6 — Мягкий CTA: человеческое, не рекламное приглашение

Критические правила:
- Максимум 6 строк на слайд, 10 слов в строке, 40-45 слов на слайд
- 1 мысль = 1 строка, короткие фразы, разговорный язык
- Тон: спокойный, экспертный, без эзотерики, без пафоса, без штампов
- «активирует парасимпатику» → заменяй на понятные формулировки
- Больше телесных сигналов и узнаваемых ситуаций
- CTA мягкий и человеческий, не рекламный
- Не увеличивай текст — лучше сократи

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
