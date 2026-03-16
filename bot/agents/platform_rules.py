"""Единый источник правил контента для всех агентов."""
from __future__ import annotations

from bot.services.brand_settings_store import get_brand_settings_cached

# ── Brand context (берётся из БД, с fallback) ──────────────────────────────
_BRAND_CONTEXT_DEFAULT = """\
Ты работаешь с брендом специалиста по регуляции нервной системы через сенсорные практики.

Контекст бренда:
- Основные инструменты: ароматерапия, медитации, гонг, звук, сенсорная настройка.
- Позиционирование: современный, бережный, телесный подход; без инфоцыганства и без \
псевдомедицинских обещаний.
- Аудитория: люди с перегрузкой, стрессом, трудностью расслабиться, а также компании, \
которым нужен мягкий wellbeing-формат для команд.
- Язык: спокойный, ясный, глубокий, человеческий. Не эзотерический туман и не сухая \
академичность.
- Запрещено: обещать лечение, ставить диагнозы, писать в стиле \
"одна практика изменит всю жизнь".
- Допустимо: говорить о состоянии, внимании к телу, переключении нервной системы, \
ритуалах восстановления, опоре через сенсорный опыт.
"""


def get_brand_context() -> str:
    """Вернуть brand_voice из БД или fallback."""
    try:
        bs = get_brand_settings_cached()
        if bs and bs.brand_voice and len(bs.brand_voice.strip()) > 50:
            return bs.brand_voice.strip()
    except Exception:
        pass
    return _BRAND_CONTEXT_DEFAULT


# ── Human writing rules (один раз, без дублирования) ──────────────────────
HUMAN_WRITING_RULES = """\
ПРАВИЛА ЧЕЛОВЕЧЕСКОГО ПИСЬМА:

Пунктуация:
- Длинное тире (—) → запятая или перенос строки (НИКОГДА не тире в постах)
- Среднее тире (–) → дефис или запятая

Запрещённые AI-штампы (не использовать и близкие варианты):
- "погружаясь в", "исследуя", "позволь себе", "это то, что"
- "мощный инструмент", "невероятный результат", "поистине", "безусловно"
- "важно отметить", "следует сказать", "хотелось бы отметить", "необходимо подчеркнуть"
- "данный", "осуществляется", "в рамках", "таким образом,", "в заключение"
- "активация парасимпатической нервной системы", "интегрировать опыт", "ресурсное состояние"

Запрещённые стилевые ошибки:
- Литературные метафоры из художественной прозы: "плечи в камне", "мысли вязнут", \
"тело как свинец"
- Рубленые слоганы и псевдопоэтические фразы: "Минует логику. Говорит телу."
- Жёсткие, неестественные конструкции: "Нервная система не спорит. Она отвечает."
- Markdown-форматирование в текстах для соцсетей: **bold**, ## заголовки, `код`
- Нумерованные списки внутри тела поста
- Горизонтальные разделители: ---, ***, ___ — НЕ использовать, абзацы разделяются только пустой строкой

Правило: если фраза звучит красиво, но неестественно в разговоре — переписать проще.
"""


# ── Platform rules: Writer (подробные структурные инструкции) ──────────────
WRITER_PLATFORM_RULES: dict[str, str] = {
    "threads": """\
Platform: Threads.
Deliver a pack of 3 posts for today: morning, day, evening.
Structure:
- Use exactly three sections in this order: УТРО, ДЕНЬ, ВЕЧЕР
- Each section is one standalone post with one idea only
- Each post must be 5-12 short lines
- Each post must be 40-120 words
- Morning: observation, thought, or insight
- Day: micro-expert post with one practical takeaway
- Evening: question to the audience, can end with an open question
- Conversational, mobile-readable, written like an in-the-moment thought
- Short lines, no walls of text, no hashtags
Forbidden: lectures, long explanations, complex terms, corporate tone, generic intros, multiple ideas in one post""",

    "instagram": """\
Platform: Instagram caption.
STRICT LIMIT: 900 characters (hashtags go on a separate line after a blank line, not counted in limit).
Structure:
- Line 1: hook (standalone line, max 15 words)
- Blank line
- Body: 2-4 short paragraphs, blank line between each
- Use ✦ or one relevant emoji per section as a visual anchor — not decorative noise
- One human CTA sentence before hashtags ("Если резонирует — напиши в ДМ" style)
- Blank line, then 5-10 hashtags
Forbidden: wall of text, hashtags in body, corporate tone, "подписывайся на нас", generic opener""",

    "telegram": """\
Platform: Telegram post.
STRICT LIMIT: 1200 characters.
Structure:
- First line: **bold hook** (use markdown ** ** for bold)
- Blank line
- Body: 2-3 paragraphs, blank line between each — deeper and more personal than Instagram
- Include one specific observation, example, or scenario
- One understated CTA at the end
NO hashtags in Telegram. Can use **bold** for 1-2 key phrases maximum.""",

    "threads_series": """\
Platform: Threads — серия из 3 постов (утро / день / вечер).
Deliver a pack of 3 posts for one day: morning, afternoon, evening.
Structure:
- Use exactly three sections in this order: УТРО, ДЕНЬ, ВЕЧЕР
- Each section is one standalone post with one idea only
- Each post must be 5-12 short lines
- Each post must be 40-120 words
- Morning: observation, thought, or first insight of the day
- Day: practical micro-tip with one concrete takeaway
- Evening: open question or gentle reflection for the audience
- Conversational, mobile-readable, human tone
- Short lines, no hashtags, no walls of text
Forbidden: lectures, complex terms, corporate tone, generic intros, multiple ideas in one post""",

    "carousel": (
        "Платформа: Instagram Карусель. 6 слайдов. "
        "SLIDE1: хук. SLIDE2: проблема. SLIDE3: механизм. "
        "SLIDE4: инсайт. SLIDE5: решение. SLIDE6: CTA."
    ),

    "default": "Короткий пост для соцсетей. Сохрани длину оригинала.",
}


# ── Platform rules: Editor (сокращённые напоминания) ──────────────────────
EDITOR_PLATFORM_RULES: dict[str, str] = {
    "threads": (
        "Платформа: Threads. Верни 3 поста на сегодня в порядке: УТРО, ДЕНЬ, ВЕЧЕР. "
        "Каждый пост — одна идея, 5-12 коротких строк, 40-120 слов, разговорный стиль, без хэштегов. "
        "Утро — наблюдение или инсайт, день — микро-экспертный пост, вечер — вопрос аудитории."
    ),
    "threads_series": (
        "Платформа: Threads, серия из 3 постов. Верни 3 поста в порядке: УТРО, ДЕНЬ, ВЕЧЕР. "
        "Каждый пост — одна идея, 5-12 коротких строк, 40-120 слов, разговорный стиль, без хэштегов. "
        "Утро — наблюдение или инсайт, день — практический совет, вечер — вопрос или размышление."
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
