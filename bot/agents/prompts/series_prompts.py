"""Prompt templates for the Content Series agents."""

from __future__ import annotations

from bot.agents.platform_rules import (
    HUMAN_WRITING_RULES as _HUMAN_WRITING_RULES,
    WRITER_PLATFORM_RULES as _PLATFORM_RULES_WRITER,
    get_brand_context,
)

ROLE_LABELS = {
    "intro": "Вступительный пост: зацепить аудиторию, обозначить тему серии, создать интригу для следующих постов",
    "middle": "Основной пост: развитие темы, конкретика, глубокое погружение",
    "climax": "Кульминационный пост: самый сильный контент, инсайт или история",
    "cta": "Финальный пост: собрать всё вместе, дать четкий CTA",
}


def outline_prompt(
    topic: str,
    goal_key: str,
    format_key: str,
    post_count: int,
    template_hint: str,
    goal_guidance: dict[str, str],
    format_labels: dict[str, str],
    rag_context: str = "",
) -> str:
    rag_block = f"\n{rag_context}\n" if rag_context else ""
    return f"""\
{get_brand_context()}
Роль: ты Content Strategist. Твоя задача: составить план серии из {post_count} постов с единой темой.

Тема серии: {topic}
Цель: {goal_guidance.get(goal_key, "Доверие")}
Формат постов: {format_labels.get(format_key, format_key)}
Шаблон: {template_hint}
{rag_block}
Составь план серии. Для каждого поста укажи номер, заголовок, угол и роль.

Верни ответ строго как JSON (без markdown-обёртки, без текста до/после):

{{
  "summary": "одно предложение, описывающее всю серию",
  "positions": [
    {{"index": 1, "title": "заголовок 3-6 слов", "angle": "угол/идея, 1 предложение", "role": "intro"}},
    {{"index": 2, "title": "...", "angle": "...", "role": "middle"}}
  ]
}}

Допустимые роли: intro, middle, climax, cta.

Правила:
- Первый пост всегда intro, последний всегда cta
- Предпоследний должен быть climax (самый сильный)
- Остальные middle
- Каждый пост должен логически вести к следующему
- Избегай пустых формулировок и повторов
- Верни ТОЛЬКО валидный JSON, ничего больше"""


def writer_batch_prompt(
    topic: str,
    goal_key: str,
    format_key: str,
    outline_text: str,
    positions: list[dict],
    previous_summaries: str,
    goal_guidance: dict[str, str],
    rag_context: str = "",
) -> str:
    rules = _PLATFORM_RULES_WRITER.get(format_key, _PLATFORM_RULES_WRITER.get("telegram", ""))
    rag_block = f"\n{rag_context}\n" if rag_context else ""
    prev_block = ""
    if previous_summaries:
        prev_block = f"\nУже написанные посты серии (краткое содержание):\n{previous_summaries}\nСледующие посты должны логически продолжать эти.\n"

    posts_spec = []
    for pos in positions:
        idx = pos["index"] + 1
        title = pos.get("title", f"Пост {idx}")
        role = pos.get("role", "middle")
        role_desc = ROLE_LABELS.get(role, ROLE_LABELS["middle"])
        posts_spec.append(f"POST {idx}: {title}\nРоль: {role_desc}")

    posts_block = "\n\n".join(posts_spec)

    return f"""\
{get_brand_context()}
Роль: ты Platform Writer. Напиши посты для контент-серии.

Тема серии: {topic}
Цель: {goal_guidance.get(goal_key, "Доверие")}

План серии:
{outline_text}
{prev_block}{rag_block}
Напиши следующие посты:

{posts_block}

{rules}

{_HUMAN_WRITING_RULES}

Верни ответ строго как JSON-массив (без markdown-обёртки, без текста до/после).
Каждый элемент массива — один пост:

[
  {{
    "index": {positions[0]["index"] + 1},
    "caption": "полный текст поста с хэштегами",
    "cta": "призыв к действию (пустая строка если уже в тексте)",
    "visual_prompt": "на английском, до 25 слов, terracotta/beige/sage palette"
  }}
]

КРИТИЧЕСКИ ВАЖНО:
- Верни ТОЛЬКО валидный JSON-массив. Никакого текста, комментариев или анализа вне JSON.
- Запрещено markdown-форматирование внутри caption: # заголовки, **жирный**, > цитаты.
- Каждый пост должен быть самодостаточным, но связан с серией.
- Между постами должна быть нарративная логика.
- Поле "index" — номер поста (начиная с 1)."""


def coherence_prompt(
    topic: str,
    posts_text: str,
    post_count: int,
) -> str:
    return f"""\
{get_brand_context()}
Роль: ты Content Editor. Проверь связность серии из {post_count} постов.

Тема серии: {topic}

Посты:
{posts_text}

Оцени серию по критериям:
1. Нарративная связность: каждый пост логически ведёт к следующему?
2. Отсутствие повторов: нет ли дублирования идей между постами?
3. Развитие темы: раскрывается ли тема глубже с каждым постом?
4. Тональная однородность: один и тот же голос бренда?
5. Сила финала: есть ли кульминация и чёткий CTA?

Верни ответ строго как JSON (без markdown-обёртки, без текста до/после):

{{
  "score": 0.85,
  "issues": ["проблема 1", "проблема 2"],
  "suggestion": "одно конкретное предложение по улучшению"
}}

Правила:
- score: число от 0.0 до 1.0, где 1.0 = идеально
- issues: пустой массив [] если проблем нет
- suggestion: пустая строка "" если предложений нет
- Верни ТОЛЬКО валидный JSON, ничего больше"""
