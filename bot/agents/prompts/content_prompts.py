"""Prompt templates for the content agent (bot/agents/content.py).

All builder functions accept the values they need as parameters
to avoid circular imports with the main content module.
"""

from __future__ import annotations

from bot.agents.platform_rules import (
    HUMAN_WRITING_RULES as _HUMAN_WRITING_RULES,
    WRITER_PLATFORM_RULES as _PLATFORM_RULES_WRITER,
    get_brand_context,
)


# ---------------------------------------------------------------------------
# Output format blocks
# ---------------------------------------------------------------------------

OUTPUT_FORMAT_THREADS = """\
Верни ответ строго как JSON (без markdown-обёртки, без текста до/после):

{
  "posts": [
    {"marker": "УТРО", "text": "текст поста, 40-70 слов, СТРОГО до 500 символов", "why_it_works": "одно предложение"},
    {"marker": "ДЕНЬ", "text": "текст поста, 40-70 слов, СТРОГО до 500 символов", "why_it_works": "одно предложение"},
    {"marker": "ВЕЧЕР", "text": "текст поста, 40-70 слов, СТРОГО до 500 символов", "why_it_works": "одно предложение"}
  ],
  "visual_prompt": "на английском, до 25 слов, terracotta/beige/sage palette, soft light, atmospheric lifestyle",
  "stock_keywords": ["keyword1", "keyword2", "keyword3"]
}

ОБЯЗАТЕЛЬНО: ровно 3 объекта в массиве posts. Пропуск любого = провал.
ЖЁСТКОЕ ОГРАНИЧЕНИЕ: каждый text НЕ БОЛЕЕ 500 символов (включая пробелы). Threads API отклонит длинный текст.
Верни ТОЛЬКО валидный JSON, ничего больше.
"""


def build_threads_output_format(template: dict) -> str:
    """Build dynamic JSON output format block based on the chosen series template."""
    slots = template["slots"]
    post_examples = []
    for s in slots:
        post_examples.append(
            f'    {{"marker": "{s["marker"]}", '
            f'"text": "текст поста, 40-70 слов, СТРОГО до 500 символов. Задача: {s["desc"]}", '
            f'"why_it_works": "одно предложение"}}'
        )
    posts_json = ",\n".join(post_examples)
    return (
        f"Верни ответ строго как JSON (без markdown-обёртки, без текста до/после):\n\n"
        f'{{\n  "posts": [\n{posts_json}\n  ],\n'
        f'  "visual_prompt": "на английском, до 25 слов, terracotta/beige/sage palette, soft light, atmospheric lifestyle",\n'
        f'  "stock_keywords": ["keyword1", "keyword2", "keyword3"]\n'
        f'}}\n\n'
        f"ОБЯЗАТЕЛЬНО: ровно {len(slots)} объектов в массиве posts. Пропуск любого = провал.\n"
        f"ЖЁСТКОЕ ОГРАНИЧЕНИЕ: каждый text НЕ БОЛЕЕ 500 символов (включая пробелы). Threads API отклонит длинный текст.\n"
        f"Все {len(slots)} постов публикуются в один день. Каждый пост — самодостаточный, но связан с остальными единой темой.\n"
        f"Верни ТОЛЬКО валидный JSON, ничего больше.\n"
    )

OUTPUT_FORMAT_DEFAULT = """\
Верни ответ строго как JSON (без markdown-обёртки, без текста до/после):

{
  "caption": "полный текст поста, начиная с хука, с хэштегами согласно правилам платформы",
  "cta": "отдельный CTA если ещё не в тексте, иначе пустая строка",
  "visual_prompt": "на английском, до 25 слов, terracotta/beige/sage palette, soft light, atmospheric lifestyle",
  "stock_keywords": ["keyword1", "keyword2", "keyword3"]
}

Верни ТОЛЬКО валидный JSON, ничего больше.
"""


def threads_output_format(format_key: str, series_template: dict | None = None) -> str:
    if format_key == "threads_series":
        if series_template:
            return build_threads_output_format(series_template)
        return OUTPUT_FORMAT_THREADS
    return OUTPUT_FORMAT_DEFAULT


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def topics_prompt(
    trends_text: str,
    goal_key: str,
    format_key: str,
    goal_guidance: dict[str, str],
    format_labels: dict[str, str],
) -> str:
    return f"""\
{get_brand_context()}
Роль: ты Content Strategist.
Цель контента: {goal_guidance[goal_key]}
Формат: {format_labels[format_key]}.

Ниже сигналы из трендов:
{trends_text}

Сгенерируй 10 тем.
Требования:
- Каждая тема должна быть привязана к состоянию, ощущению в теле, ритуалу восстановления или практическому применению.
- Подходящие углы: стресс, перегрузка, сон, заземление, сенсорные ритуалы, корпоративный wellbeing, аромат как якорь состояния, гонг как способ замедления.
- Избегай пустых общих формулировок и слишком мистического языка.
- Формулируй так, чтобы тема подходила под выбранную цель.

Верни строго нумерованный список без пояснений:
1. ...
10. ...
"""


def custom_topics_prompt(
    user_brief: str,
    goal_key: str,
    format_key: str,
    goal_guidance: dict[str, str],
    format_labels: dict[str, str],
) -> str:
    return f"""\
{get_brand_context()}
Роль: ты Content Strategist.
Цель контента: {goal_guidance[goal_key]}
Формат: {format_labels[format_key]}.

Ниже пользовательское направление для контента:
{user_brief[:2000]}

Сгенерируй 10 тем.
Требования:
- Сохраняй связь с нишей: регуляция нервной системы, сенсорные практики, ароматерапия, медитации, гонг.
- Раскрой пользовательский запрос через конкретные углы, состояния, жизненные ситуации или сценарии применения.
- Избегай пустых и общих названий.
- Формулируй так, чтобы тема подходила под выбранную цель и формат.

Верни строго нумерованный список без пояснений:
1. ...
10. ...
"""


PRACTICE_FOCUS_BLOCKS = {
    "aroma": "",
    "bodywork": (
        "\nФокус практики: РАБОТА С ТЕЛОМ (массаж, остеопрактика, биодинамика, миофасциальный релиз).\n"
        "Подход: раскрой, как аромат поддерживает тело в процессе телесной практики. "
        "Упоминай конкретные техники (массаж, растяжка, точечное давление), зоны тела и связь масел с телесным опытом. "
        "Аудитория — массажисты, остеопрактики, специалисты по движению.\n"
    ),
    "sound": (
        "\nФокус практики: ЗВУК И ВИБРАЦИЯ (поющие чаши, гонг, камертон, бинауральные ритмы, голосовые практики).\n"
        "Подход: раскрой синергию аромата и звуковой вибрации. "
        "Упоминай конкретные инструменты (чаша, гонг), частоты, резонансы и связь масел со звуковым опытом. "
        "Аудитория — звукотерапевты, практики гонг-медитации, специалисты по вибрационному целительству.\n"
    ),
}


def strategist_prompt(
    topic: str,
    goal_key: str,
    format_key: str,
    goal_guidance: dict[str, str],
    format_labels: dict[str, str],
    blend_context: dict | None = None,
    rag_context: str = "",
    practice_focus: str = "aroma",
) -> str:
    blend_block = ""
    if blend_context:
        from bot.agents.blend_content_context import build_blend_strategist_block

        blend_block = (
            "\nКонтекст смеси:\n" + build_blend_strategist_block(blend_context) + "\n"
            "Угол должен раскрывать воздействие смеси через её профиль.\n"
        )
    rag_block = f"\n{rag_context}\n" if rag_context else ""
    focus_block = PRACTICE_FOCUS_BLOCKS.get(practice_focus, "")
    return f"""\
{get_brand_context()}
Роль: ты Content Strategist. Твоя задача — найти угол и убийственную первую строку.

Тема: {topic}
Цель: {goal_guidance[goal_key]}
Формат: {format_labels[format_key]}
{focus_block}{rag_block}

ПАТТЕРНЫ СИЛЬНЫХ ХУКОВ (используй один из них):
1. Контринтуитивное утверждение: «Чем больше ты стараешься расслабиться, тем сильнее зажимаешься»
2. Конкретная ситуация-триггер: «Ты лежишь в кровати, телефон заряжается, а голова нет»
3. Неожиданный факт: «Лаванда, которую тебе советуют от бессонницы, может её усилить»
4. Провокационный вопрос: «А что если твой "стресс" — это просто тело, которое забыло, как дышать?»
5. Признание/уязвимость: «Я три года рассказывала про дыхание, а сама не могла выдохнуть после рабочего дня»
6. Разрушение мифа: «"Эфирные масла лечат" — нет. Но они умеют кое-что полезнее»

ANTI-PATTERNS (так писать ЗАПРЕЩЕНО):
- «В современном мире стресс стал...» — скучное начало, все пролистнут
- «Сегодня хочу поделиться...» — не интригует
- «Задумывались ли вы...» — избитый шаблон
- «Каждый из нас...» — обезличено, не цепляет
- «Ароматерапия — это...» — лекция, а не хук
- Любое начало с определения или объяснения термина

Ответь строго в формате (два поля, на русском):
ANGLE: [1-2 предложения — почему эта тема резонирует СЕЙЧАС с этой аудиторией и под эту цель]
HOOK: [точная первая строка поста — останавливает скролл. Должна вызывать реакцию «ого» или «это про меня»]

Пунктуация: тире (— –) → запятая. Запрещено: "важно отметить", "данный", "осуществляется", "в рамках", markdown-форматирование.
{blend_block}"""


def suggest_topics_prompt(
    goal_key: str,
    format_key: str,
    exclude_topics: list[str],
    goal_guidance: dict[str, str],
    format_labels: dict[str, str],
) -> str:
    exclude_block = ""
    if exclude_topics:
        items = "\n".join(f"- {t}" for t in exclude_topics[:30])
        exclude_block = f"\n\nНЕ повторяй темы похожие на:\n{items}\n"
    return f"""\
{get_brand_context()}
Роль: ты Content Strategist.
Цель контента: {goal_guidance.get(goal_key, goal_guidance["trust"])}
Формат: {format_labels.get(format_key, format_key)}.

Сгенерируй 5 тем для контента.
Требования:
- Каждая тема должна быть привязана к состоянию, ощущению в теле, ритуалу восстановления или практическому применению.
- Подходящие углы: стресс, перегрузка, сон, заземление, сенсорные ритуалы, корпоративный wellbeing, аромат как якорь состояния, гонг как способ замедления.
- Избегай пустых общих формулировок и слишком мистического языка.
- Формулируй так, чтобы тема подходила под выбранную цель.
{exclude_block}
Верни строго нумерованный список без пояснений:
1. ...
5. ...
"""


def writer_prompt(
    topic: str,
    goal_key: str,
    format_key: str,
    angle: str,
    hook: str,
    goal_guidance: dict[str, str],
    blend_context: dict | None = None,
    rag_context: str = "",
    practice_focus: str = "aroma",
    series_template: dict | None = None,
) -> str:
    rules = _PLATFORM_RULES_WRITER.get(format_key, _PLATFORM_RULES_WRITER["telegram"])
    blend_block = ""
    if blend_context:
        from bot.agents.blend_content_context import build_blend_writer_block

        blend_block = (
            "\nКонтекст смеси:\n" + build_blend_writer_block(blend_context) + "\n"
            "Правила для текста о смеси:\n"
            "- Начни с состояния, к которому ведёт смесь\n"
            "- Упомяни 1-2 масла с ролью и свойством\n"
            "- Объясни синергию\n"
            "- Включи способ применения\n"
            "- Это рассказ, не рецепт\n"
        )
    rag_block = f"\n{rag_context}\n" if rag_context else ""
    focus_block = PRACTICE_FOCUS_BLOCKS.get(practice_focus, "")
    return f"""\
{get_brand_context()}
Роль: ты Platform Writer. Ты получил угол и хук от стратега. Напиши готовый пост.

Тема: {topic}
Цель: {goal_guidance[goal_key]}
Стратегический угол: {angle}
Первая строка (хук): {hook}
{focus_block}{blend_block}{rag_block}
{rules}

Дополнительные правила письма:
- Пиши так, как это реально сказал бы живой человек в заметке или посте, а не копирайтер в презентации.
- Одна мысль должна естественно вести к следующей. Без резких обрывов, пафосных формул и "умных" коротких тезисов.
- Не используй вычурные или слишком жёсткие фразы ради эффекта. Если фраза звучит как слоган, перепиши проще.
- Никаких литературных метафор. Используй слова из обычной речи, не из художественной прозы. Плохо: "плечи в камне", "тело как свинец", "душа не отпускает". Хорошо: "плечи не расслабляются", "не можешь уснуть", "голова не отключается".
- Дай один конкретный жизненный момент или наблюдение, чтобы текст стоял на земле.
- Предпочитай простые слова и нормальный человеческий ритм. Не пиши так, будто текст старается впечатлить.

{_HUMAN_WRITING_RULES}

КРИТИЧЕСКИ ВАЖНО:
- Верни ТОЛЬКО готовый текст поста. НЕ добавляй разбор, анализ, комментарии, объяснения, заголовки типа "# Разбор текста" или "## Что здесь сильного".
- Запрещено использовать markdown-форматирование: # заголовки, **жирный**, > цитаты, ``` код. Посты для соцсетей пишутся простым текстом.
- Если ты вернёшь анализ или разбор вместо текста поста — это провал задания.

{threads_output_format(format_key, series_template=series_template)}"""
