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

FORMAT_GUIDANCE = {
    "threads": "Короткий живой пост до 450 символов. Сильный хук, плотный ритм, финальный вопрос или CTA.",
    "instagram": "Подпись до 900 символов. Можно чуть больше воздуха, но без длинных заходов.",
    "telegram": "Пост до 1200 символов. Чуть глубже, чем в соцсетях, но все еще компактно и читабельно.",
    "carousel": "5 слайдов: хук, 3 смысловых слайда, CTA. Каждый слайд короткий и визуально пригодный.",
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
        if probe.startswith("ANGLE:"):
            draft.angle = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "angle"
        elif probe.startswith("HOOK:"):
            draft.hook = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "hook"
        elif probe.startswith("CAPTION:"):
            draft.caption = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "caption"
        elif probe.startswith("CTA:"):
            draft.cta = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "cta"
        elif probe.startswith("HASHTAGS:"):
            draft.hashtags = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "hashtags"
        elif probe.startswith("VISUAL_PROMPT:"):
            draft.visual_prompt = _fix_dashes(probe.split(":", 1)[1].strip())
            current_field = "visual_prompt"
        else:
            matched_slide = False
            for idx in range(1, 6):
                if probe.startswith(f"SLIDE{idx}:"):
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
        draft.angle,
        draft.hook,
        draft.caption,
        draft.cta,
        draft.hashtags,
        draft.visual_prompt,
        draft.slides,
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


def _topics_prompt(trends_text: str, goal_key: str, format_key: str) -> str:
    return f"""\
{BRAND_CONTEXT}

Роль: ты Content Strategist.
Цель контента: {GOAL_GUIDANCE[goal_key]}
Формат: {FORMAT_LABELS[format_key]}. {FORMAT_GUIDANCE[format_key]}

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
Формат: {FORMAT_LABELS[format_key]}. {FORMAT_GUIDANCE[format_key]}

Ниже пользовательское направление для контента:
{user_brief}

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


def _draft_prompt(topic: str, goal_key: str, format_key: str) -> str:
    base = f"""\
{BRAND_CONTEXT}

Роль: ты связка из 3 агентов:
1. Trend Analyst - понимает, почему тема резонирует сейчас.
2. Platform Writer - пишет нативно под площадку.
3. Brand Guardian - убирает манипуляции, магическое мышление и медицинские обещания.

Тема: {topic}
Цель контента: {GOAL_GUIDANCE[goal_key]}
Формат: {FORMAT_LABELS[format_key]}. {FORMAT_GUIDANCE[format_key]}

Собери готовый контент-пакет.
Общие требования:
- Писать по-русски.
- От первого лица или в теплом экспертном голосе.
- Без клише, без "просто позволь себе", без агрессивного прогрева.
- Текст должен звучать современно и вручную.
- CTA мягкий, но конкретный.
- VISUAL_PROMPT пиши на английском, до 30 слов.
"""
    if format_key == "carousel":
        extra = """\
Верни строго в формате:
ANGLE: ...
HOOK: ...
SLIDE1: ...
SLIDE2: ...
SLIDE3: ...
SLIDE4: ...
SLIDE5: ...
CTA: ...
HASHTAGS: ...
VISUAL_PROMPT: ...
"""
    else:
        extra = """\
Верни строго в формате:
ANGLE: ...
HOOK: ...
CAPTION: ...
CTA: ...
HASHTAGS: ...
VISUAL_PROMPT: ...
"""
    return base + "\n" + extra


def _call_claude(prompt: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
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


def _generate_draft_sync(topic: str, goal_key: str, format_key: str) -> ContentDraft:
    from bot.agents.creative_team import edit_post_sync

    raw = _call_claude(_draft_prompt(topic, goal_key, format_key), max_tokens=1200)
    draft = parse_content_draft(raw)
    if not _has_structured_content(draft) and raw.strip():
        draft.caption = _fix_dashes(raw.strip())

    # Editor pass: sharpen hook and caption
    if format_key != "carousel":
        if draft.hook:
            draft.hook = edit_post_sync(draft.hook, topic, platform=format_key)
        if draft.caption:
            draft.caption = edit_post_sync(draft.caption, topic, platform=format_key)
    return draft


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


async def generate_content_draft(topic: str, goal_key: str, format_key: str) -> ContentDraft:
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
