from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from analytics.base import SourceResult
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
    "instagram": "Instagram",
    "telegram": "Telegram",
    "carousel": "Карусель",
}

# Detailed per-platform writing rules for the Writer agent
_PLATFORM_RULES_WRITER = {
    "threads": """\
Platform: Threads.
STRICT LIMIT: 450 characters total including hashtags.
Structure:
- Line 1: the hook — verbatim or tightened, max 12 words, no greeting, no "Сегодня хочу"
- Body: 2-3 dense sentences. Specific and concrete, no filler transitions
- Last line: question to reader OR one-sentence CTA ("Напиши в ДМ если откликается")
- New line, then 3-5 hashtags
Forbidden: "В нашем мире", long intros, multiple CTAs, "подписывайся", empty filler""",

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
}

BRAND_CONTEXT = """\
Ты работаешь с брендом специалиста по регуляции нервной системы через сенсорные практики.

Контекст бренда:
- Основные инструменты: ароматерапия, медитации, гонг, звук, сенсорная настройка.
- Позиционирование: современный, бережный, телесный подход; без инфоцыганства и без псевдомедицинских обещаний.
- Аудитория: люди с перегрузкой, стрессом, трудностью расслабиться, а также компании, которым нужен мягкий wellbeing-формат для команд.
- Язык: спокойный, ясный, глубокий, человеческий. Не эзотерический туман и не сухая академичность.
- Запрещено: обещать лечение, ставить диагнозы, писать в стиле "одна практика изменит всю жизнь".
- Допустимо: говорить о состоянии, внимании к телу, переключении нервной системы, ритуалах восстановления, опоре через сенсорный опыт.
"""


@dataclass
class ContentDraft:
    angle: str = ""
    hook: str = ""
    caption: str = ""
    cta: str = ""
    hashtags: str = ""
    visual_prompt: str = ""
    slides: list[str] = field(default_factory=list)


def goal_label(goal_key: str) -> str:
    return GOAL_LABELS.get(goal_key, goal_key)


def format_label(format_key: str) -> str:
    return FORMAT_LABELS.get(format_key, format_key)


def _fix_dashes(text: str) -> str:
    return text.replace("\u2014", "-").replace("\u2013", "-")


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
            items.append(_fix_dashes(line.split(". ", 1)[1].strip()))
    return items[:limit]


def parse_content_draft(raw: str) -> ContentDraft:
    draft = ContentDraft()
    current_field = ""
    for line in raw.strip().splitlines():
        line = line.strip()
        probe = line.removeprefix("- ").strip()
        probe = probe.replace("**", "").replace("__", "").strip()
        if probe.upper().startswith("ANGLE:"):
            draft.angle = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "angle"
        elif probe.upper().startswith("HOOK:"):
            draft.hook = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "hook"
        elif probe.upper().startswith("CAPTION:"):
            draft.caption = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "caption"
        elif probe.upper().startswith("CTA:"):
            draft.cta = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "cta"
        elif probe.upper().startswith("HASHTAGS:"):
            draft.hashtags = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "hashtags"
        elif probe.upper().startswith("VISUAL_PROMPT:"):
            draft.visual_prompt = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "visual_prompt"
        else:
            matched_slide = False
            for idx in range(1, 6):
                if probe.upper().startswith(f"SLIDE{idx}:"):
                    draft.slides.append(_fix_dashes(probe.split(":", 1)[1].strip()))
                    current_field = ""
                    matched_slide = True
                    break
            if matched_slide or not line:
                continue
            if current_field == "caption":
                draft.caption = "\n".join(filter(None, [draft.caption, _fix_dashes(line)]))
            elif current_field == "angle":
                draft.angle = "\n".join(filter(None, [draft.angle, _fix_dashes(line)]))
            elif current_field == "hook":
                draft.hook = "\n".join(filter(None, [draft.hook, _fix_dashes(line)]))
            elif current_field == "cta":
                draft.cta = "\n".join(filter(None, [draft.cta, _fix_dashes(line)]))
            elif current_field == "hashtags":
                draft.hashtags = "\n".join(filter(None, [draft.hashtags, _fix_dashes(line)]))
            elif current_field == "visual_prompt":
                draft.visual_prompt = "\n".join(filter(None, [draft.visual_prompt, _fix_dashes(line)]))
    return draft


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
{BRAND_CONTEXT}
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
{BRAND_CONTEXT}
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
{BRAND_CONTEXT}
Роль: ты Content Strategist. Твоя задача — найти угол и первую строку.

Тема: {topic}
Цель: {GOAL_GUIDANCE[goal_key]}
Формат: {FORMAT_LABELS[format_key]}

Ответь строго в формате (два поля, на русском):
ANGLE: [1-2 предложения — почему эта тема резонирует СЕЙЧАС с этой аудиторией и под эту цель]
HOOK: [точная первая строка поста — останавливает скролл, без приветствий, без "Сегодня хочу поделиться"]
"""


def _writer_prompt(topic: str, goal_key: str, format_key: str, angle: str, hook: str) -> str:
    rules = _PLATFORM_RULES_WRITER.get(format_key, _PLATFORM_RULES_WRITER["telegram"])
    return f"""\
{BRAND_CONTEXT}
Роль: ты Platform Writer. Ты получил угол и хук от стратега. Напиши готовый пост.

Тема: {topic}
Цель: {GOAL_GUIDANCE[goal_key]}
Стратегический угол: {angle}
Первая строка (хук): {hook}

{rules}

Верни строго в формате:
CAPTION: [полный текст поста, начиная с хука, с хэштегами согласно правилам платформы]
CTA: [отдельный CTA если ещё не в тексте, иначе пусто]
VISUAL_PROMPT: [на английском, до 25 слов, terracotta/beige/sage palette, soft light, atmospheric lifestyle]
"""


# ── Agent functions ──────────────────────────────────────────────────────────

def _call_claude(prompt: str, max_tokens: int, system: str = "") -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    kwargs: dict = dict(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text.strip()


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
            angle = _fix_dashes(cleaned.split(":", 1)[1].strip())
        elif cleaned.upper().startswith("HOOK:"):
            hook = _fix_dashes(cleaned.split(":", 1)[1].strip())
    # Fallback: use raw output as angle if parsing failed
    return angle or raw[:200], hook


def _generate_writer_sync(
    topic: str, goal_key: str, format_key: str, angle: str, hook: str
) -> ContentDraft:
    """Step 2: Writer produces platform-native draft. Step 3: Editor polishes."""
    from bot.agents.creative_team import edit_post_sync

    raw = _call_claude(
        _writer_prompt(topic, goal_key, format_key, angle, hook), max_tokens=900
    )
    draft = parse_content_draft(raw)
    draft.angle = angle
    if not draft.hook:
        draft.hook = hook

    if not _has_structured_content(draft) and raw.strip():
        draft.caption = _fix_dashes(raw.strip())

    # Step 3: Editor pass
    if draft.caption:
        draft.caption = edit_post_sync(draft.caption, topic, platform=format_key)

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
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _generate_topics_sync, results, goal_key, format_key, user_brief
    )


async def generate_strategist_step(
    topic: str, goal_key: str, format_key: str
) -> tuple[str, str]:
    """Returns (angle, hook) — exposes step 1 for progress display in handler."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _generate_strategist_sync, topic, goal_key, format_key
    )


async def generate_writer_step(
    topic: str, goal_key: str, format_key: str, angle: str, hook: str
) -> ContentDraft:
    """Returns ContentDraft — exposes step 2+3 for progress display in handler."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _generate_writer_sync, topic, goal_key, format_key, angle, hook
    )


async def generate_content_draft(topic: str, goal_key: str, format_key: str) -> ContentDraft:
    """Full 3-agent chain as a single async call."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _generate_draft_sync, topic, goal_key, format_key)


def generate_image_bytes(prompt: str) -> bytes | None:
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.image_api_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                return part.inline_data.data
    except Exception:
        return None
    return None
