from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from analytics.base import SourceResult
from bot.agents.platform_rules import (
    HUMAN_WRITING_RULES as _HUMAN_WRITING_RULES,
    WRITER_PLATFORM_RULES as _PLATFORM_RULES_WRITER,
    get_brand_context,
)
from bot.services.gemini_images import generate_gemini_image_sync
from bot.services.humanizer import humanize
from config import settings

_executor = ThreadPoolExecutor(max_workers=2)

GOAL_LABELS = {
    "sales": "Продажа",
    "engagement": "Вовлечение",
    "trust": "Доверие",
    "authority": "Экспертность",
}

GOAL_GUIDANCE = {
    "sales": "Мягко подводить к заявке на сессию, корпоративный wellness или личную практику.",
    "engagement": "Запускать обсуждение, сохраняемость и репосты без дешевой провокации.",
    "trust": "Показывать глубину подхода, безопасность и бережность работы с состоянием.",
    "authority": "Подсвечивать метод, наблюдения и профессиональную рамку без занудства.",
}

FORMAT_LABELS = {
    "threads": "Threads",
    "threads_series": "Серия Threads",
    "instagram": "Instagram",
    "telegram": "Telegram",
    "carousel": "Карусель",
}

# Backward compat re-export
BRAND_CONTEXT = get_brand_context


@dataclass
class ContentDraft:
    angle: str = ""
    hook: str = ""
    caption: str = ""
    cta: str = ""
    hashtags: str = ""
    visual_prompt: str = ""
    slides: list[str] = field(default_factory=list)
    quality_score: dict | None = None


def goal_label(goal_key: str) -> str:
    return GOAL_LABELS.get(goal_key, goal_key)


def format_label(format_key: str) -> str:
    return FORMAT_LABELS.get(format_key, format_key)


def _format_trends(results: list[SourceResult]) -> str:
    parts: list[str] = []
    for result in results:
        if not result.items or result.source_key == "ai_recommendations":
            continue
        lines = [f"- {item.title[:90]} {item.score}".strip() for item in result.items[:3]]
        parts.append(f"{result.source_name}:\n" + "\n".join(lines))
    return "\n\n".join(parts[:12])


def parse_numbered_list(raw: str, limit: int = 10) -> list[str]:
    items: list[str] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            items.append(humanize(line.split(". ", 1)[1].strip()))
    return items[:limit]


def parse_content_draft(raw: str) -> ContentDraft:
    draft = ContentDraft()
    current_field = ""
    for line in raw.strip().splitlines():
        line = line.strip()
        probe = line.removeprefix("- ").strip()
        probe = probe.replace("**", "").replace("__", "").strip()
        if probe.upper().startswith("ANGLE:"):
            draft.angle = humanize(probe.split(":", 1)[1].strip())
            current_field = "angle"
        elif probe.upper().startswith("HOOK:"):
            draft.hook = humanize(probe.split(":", 1)[1].strip())
            current_field = "hook"
        elif probe.upper().startswith("CAPTION:"):
            draft.caption = humanize(probe.split(":", 1)[1].strip())
            current_field = "caption"
        elif probe.upper().startswith("CTA:"):
            draft.cta = humanize(probe.split(":", 1)[1].strip())
            current_field = "cta"
        elif probe.upper().startswith("HASHTAGS:"):
            draft.hashtags = humanize(probe.split(":", 1)[1].strip())
            current_field = "hashtags"
        elif probe.upper().startswith("VISUAL_PROMPT:"):
            draft.visual_prompt = humanize(probe.split(":", 1)[1].strip())
            current_field = "visual_prompt"
        else:
            matched_slide = False
            for idx in range(1, 6):
                if probe.upper().startswith(f"SLIDE{idx}:"):
                    draft.slides.append(humanize(probe.split(":", 1)[1].strip()))
                    current_field = ""
                    matched_slide = True
                    break
            if matched_slide or not line:
                continue
            if current_field == "caption":
                draft.caption = "\n".join(filter(None, [draft.caption, humanize(line)]))
            elif current_field == "angle":
                draft.angle = "\n".join(filter(None, [draft.angle, humanize(line)]))
            elif current_field == "hook":
                draft.hook = "\n".join(filter(None, [draft.hook, humanize(line)]))
            elif current_field == "cta":
                draft.cta = "\n".join(filter(None, [draft.cta, humanize(line)]))
            elif current_field == "hashtags":
                draft.hashtags = "\n".join(filter(None, [draft.hashtags, humanize(line)]))
            elif current_field == "visual_prompt":
                draft.visual_prompt = "\n".join(filter(None, [draft.visual_prompt, humanize(line)]))
    return draft


_THREADS_SLOTS = [
    {"slot": "morning", "label": "УТРО", "marker": "УТРО"},
    {"slot": "day", "label": "ДЕНЬ", "marker": "ДЕНЬ"},
    {"slot": "evening", "label": "ВЕЧЕР", "marker": "ВЕЧЕР"},
]

_THREADS_DEFAULT_TIMES = {"morning": "09:00", "day": "13:00", "evening": "19:00"}


def split_threads_posts(caption: str) -> list[dict[str, str]]:
    """Split a threads caption containing УТРО/ДЕНЬ/ВЕЧЕР sections into 3 posts."""
    import re

    posts: list[dict[str, str]] = []
    markers = [s["marker"] for s in _THREADS_SLOTS]
    pattern = "|".join(re.escape(m) for m in markers)
    parts = re.split(rf"(?:^|\n)\s*(?:\*\*)?({pattern})(?:\*\*)?[:\s]*\n?", caption, flags=re.IGNORECASE)

    slot_texts: dict[str, str] = {}
    i = 1
    while i < len(parts) - 1:
        marker = parts[i].strip().upper()
        text = parts[i + 1].strip()
        for s in _THREADS_SLOTS:
            if s["marker"] == marker:
                slot_texts[s["slot"]] = text
                break
        i += 2

    for slot_info in _THREADS_SLOTS:
        posts.append({
            "slot": slot_info["slot"],
            "label": slot_info["label"],
            "text": slot_texts.get(slot_info["slot"], ""),
            "default_time": _THREADS_DEFAULT_TIMES[slot_info["slot"]],
        })

    return posts


def _has_structured_content(draft: ContentDraft) -> bool:
    return any([
        draft.angle, draft.hook, draft.caption,
        draft.cta, draft.hashtags, draft.visual_prompt, draft.slides,
    ])


def format_content_message(draft: ContentDraft, topic: str, goal_key: str, format_key: str) -> str:
    lines = [
        f"🎯 Цель: {goal_label(goal_key)}",
        f"🧩 Формат: {format_label(format_key)}",
        f"🪄 Тема: {topic}",
    ]
    if draft.angle:
        lines.append(f"\nANGLE:\n{draft.angle}")
    if draft.hook:
        lines.append(f"\nHOOK:\n{draft.hook}")
    if format_key == "carousel" and draft.slides:
        slides_text = "\n".join(f"{i}. {slide}" for i, slide in enumerate(draft.slides, 1))
        lines.append(f"\nSLIDES:\n{slides_text}")
    elif draft.caption:
        lines.append(f"\nTEXT:\n{draft.caption}")
    if draft.cta:
        lines.append(f"\nCTA:\n{draft.cta}")
    if draft.hashtags:
        lines.append(f"\nHASHTAGS:\n{draft.hashtags}")
    if draft.visual_prompt:
        lines.append(f"\nVISUAL PROMPT:\n{draft.visual_prompt}")
    return "\n".join(lines)


def make_slide_prompts_with_text(base: str, slides: list[str]) -> str:
    lines = ["Промпты для карусели (картинка с текстом):\n"]
    for idx, slide in enumerate(slides, 1):
        lines.append(
            f"Слайд {idx}: {base}, visual theme: {slide[:90]}, text overlay: \"{slide}\", clean editorial composition"
        )
    return "\n".join(lines)


def make_slide_prompts_no_text(base: str, slides: list[str]) -> str:
    lines = ["Промпты для карусели (чистый фон, без текста):\n"]
    for idx, slide in enumerate(slides, 1):
        lines.append(
            f"Слайд {idx}: {base}, visual theme: {slide[:90]}, clean minimal background, negative space for text, no typography"
        )
    return "\n".join(lines)


def make_single_image_prompt(base: str, text: str, with_text: bool) -> str:
    if with_text:
        return f"{base}, visual theme: {text[:90]}, text overlay: \"{text}\", clean editorial composition"
    return f"{base}, visual theme: {text[:90]}, clean minimal background, negative space for text, no typography"


# ── Prompts ──────────────────────────────────────────────────────────────────

def _topics_prompt(trends_text: str, goal_key: str, format_key: str) -> str:
    return f"""\
{get_brand_context()}
Роль: ты Content Strategist.
Цель контента: {GOAL_GUIDANCE[goal_key]}
Формат: {FORMAT_LABELS[format_key]}.

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


def _custom_topics_prompt(user_brief: str, goal_key: str, format_key: str) -> str:
    return f"""\
{get_brand_context()}
Роль: ты Content Strategist.
Цель контента: {GOAL_GUIDANCE[goal_key]}
Формат: {FORMAT_LABELS[format_key]}.

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


def _strategist_prompt(topic: str, goal_key: str, format_key: str) -> str:
    return f"""\
{get_brand_context()}
Роль: ты Content Strategist. Твоя задача — найти угол и первую строку.

Тема: {topic}
Цель: {GOAL_GUIDANCE[goal_key]}
Формат: {FORMAT_LABELS[format_key]}

Ответь строго в формате (два поля, на русском):
ANGLE: [1-2 предложения — почему эта тема резонирует СЕЙЧАС с этой аудиторией и под эту цель]
HOOK: [точная первая строка поста — останавливает скролл, без приветствий, без "Сегодня хочу поделиться"]

Пунктуация: тире (— –) → запятая. Запрещено: "важно отметить", "данный", "осуществляется", "в рамках", markdown-форматирование.
"""


def _writer_prompt(topic: str, goal_key: str, format_key: str, angle: str, hook: str) -> str:
    rules = _PLATFORM_RULES_WRITER.get(format_key, _PLATFORM_RULES_WRITER["telegram"])
    return f"""\
{get_brand_context()}
Роль: ты Platform Writer. Ты получил угол и хук от стратега. Напиши готовый пост.

Тема: {topic}
Цель: {GOAL_GUIDANCE[goal_key]}
Стратегический угол: {angle}
Первая строка (хук): {hook}

{rules}

Дополнительные правила письма:
- Пиши так, как это реально сказал бы живой человек в заметке или посте, а не копирайтер в презентации.
- Одна мысль должна естественно вести к следующей. Без резких обрывов, пафосных формул и "умных" коротких тезисов.
- Не используй вычурные или слишком жёсткие фразы ради эффекта. Если фраза звучит как слоган, перепиши проще.
- Никаких литературных метафор. Используй слова из обычной речи, не из художественной прозы. Плохо: "плечи в камне", "тело как свинец", "душа не отпускает". Хорошо: "плечи не расслабляются", "не можешь уснуть", "голова не отключается".
- Дай один конкретный жизненный момент или наблюдение, чтобы текст стоял на земле.
- Предпочитай простые слова и нормальный человеческий ритм. Не пиши так, будто текст старается впечатлить.

{_HUMAN_WRITING_RULES}

Верни строго в формате:
CAPTION: [полный текст поста, начиная с хука, с хэштегами согласно правилам платформы]
CTA: [отдельный CTA если ещё не в тексте, иначе пусто]
VISUAL_PROMPT: [на английском, до 25 слов, terracotta/beige/sage palette, soft light, atmospheric lifestyle]
"""


# ── Agent functions ──────────────────────────────────────────────────────────

def _call_claude(prompt: str, max_tokens: int, system: str = "") -> str:
    from bot.services.claude_client import call_claude

    return call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        system=system,
        context="content agent",
    )


def _generate_topics_sync(
    results: list[SourceResult] | None,
    goal_key: str,
    format_key: str,
    user_brief: str = "",
) -> list[str]:
    if user_brief:
        prompt = _custom_topics_prompt(user_brief, goal_key, format_key)
    else:
        trends_text = _format_trends(results or [])
        prompt = _topics_prompt(trends_text, goal_key, format_key)
    raw = _call_claude(prompt, max_tokens=900)
    return parse_numbered_list(raw, limit=10)


def _generate_strategist_sync(topic: str, goal_key: str, format_key: str) -> tuple[str, str]:
    """Step 1: Strategist finds creative angle and hook line."""
    raw = _call_claude(_strategist_prompt(topic, goal_key, format_key), max_tokens=250)
    angle = ""
    hook = ""
    for line in raw.strip().splitlines():
        line = line.strip()
        cleaned = line.replace("**", "").replace("__", "").strip()
        if cleaned.upper().startswith("ANGLE:"):
            angle = humanize(cleaned.split(":", 1)[1].strip())
        elif cleaned.upper().startswith("HOOK:"):
            hook = humanize(cleaned.split(":", 1)[1].strip())
    # Fallback: use raw output as angle if parsing failed
    return angle or raw[:200], hook


_MAX_QUALITY_RETRIES = 2


def _generate_writer_sync(
    topic: str, goal_key: str, format_key: str, angle: str, hook: str
) -> ContentDraft:
    """Step 2: Writer produces platform-native draft. Step 3: Editor polishes."""
    from bot.agents.creative_team import edit_post_sync

    token_limit = 1200 if format_key in ("threads", "threads_series") else 900
    raw = _call_claude(
        _writer_prompt(topic, goal_key, format_key, angle, hook), max_tokens=token_limit
    )
    draft = parse_content_draft(raw)
    draft.angle = angle
    if not draft.hook:
        draft.hook = hook

    if not _has_structured_content(draft) and raw.strip():
        draft.caption = humanize(raw.strip())

    # Step 3: Editor pass
    if draft.caption:
        draft.caption = edit_post_sync(draft.caption, topic, platform=format_key)

    # Step 4: Quality evaluation with retry
    from bot.agents.quality_evaluator import _evaluate_sync
    score = None
    for attempt in range(_MAX_QUALITY_RETRIES):
        if not draft.caption:
            break
        score = _evaluate_sync(draft.caption, format_key, topic)
        if score["passed"]:
            break
        if attempt < _MAX_QUALITY_RETRIES - 1:
            critique_prompt = (
                f"{_writer_prompt(topic, goal_key, format_key, angle, hook)}\n\n"
                f"Предыдущая версия получила низкую оценку. Критика редактора:\n"
                f"{score['critique']}\n\n"
                f"Перепиши текст учитывая это замечание. "
                f"Сохрани угол и хук, но улучши то, что указано в критике."
            )
            raw2 = _call_claude(critique_prompt, max_tokens=token_limit)
            draft2 = parse_content_draft(raw2)
            if draft2.caption:
                draft2.caption = edit_post_sync(draft2.caption, topic, platform=format_key)
                draft2.angle = angle
                draft2.hook = hook
                draft = draft2

    if score is not None:
        draft.quality_score = dict(score)

    return draft


def _generate_draft_sync(topic: str, goal_key: str, format_key: str) -> ContentDraft:
    """Full 3-agent chain: Strategist → Writer → Editor."""
    angle, hook = _generate_strategist_sync(topic, goal_key, format_key)
    return _generate_writer_sync(topic, goal_key, format_key, angle, hook)


# ── Public async API ─────────────────────────────────────────────────────────

async def generate_topic_options(
    results: list[SourceResult] | None,
    goal_key: str,
    format_key: str,
    user_brief: str = "",
) -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor, _generate_topics_sync, results, goal_key, format_key, user_brief
    )


async def generate_strategist_step(
    topic: str, goal_key: str, format_key: str
) -> tuple[str, str]:
    """Returns (angle, hook) — exposes step 1 for progress display in handler."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor, _generate_strategist_sync, topic, goal_key, format_key
    )


async def generate_writer_step(
    topic: str, goal_key: str, format_key: str, angle: str, hook: str
) -> ContentDraft:
    """Returns ContentDraft — exposes step 2+3 for progress display in handler."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor, _generate_writer_sync, topic, goal_key, format_key, angle, hook
    )


async def generate_content_draft(topic: str, goal_key: str, format_key: str) -> ContentDraft:
    """Full 3-agent chain as a single async call."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _generate_draft_sync, topic, goal_key, format_key)


def generate_image_bytes(prompt: str) -> bytes | None:
    return generate_gemini_image_sync(prompt, log_context="Gemini content image")
