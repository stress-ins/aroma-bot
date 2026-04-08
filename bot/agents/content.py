from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from analytics.base import SourceResult
from bot.agents.platform_rules import (
    HUMAN_WRITING_RULES as _HUMAN_WRITING_RULES,
    WRITER_PLATFORM_RULES as _PLATFORM_RULES_WRITER,
    get_brand_context,
)
from bot.services.gemini_images import generate_gemini_image_sync
from bot.services.humanizer import humanize
from bot.utils.json_parser import extract_json
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
    stock_keywords: list[str] = field(default_factory=list)
    slides: list[str] = field(default_factory=list)
    quality_score: dict | None = None
    series_template_key: str = ""
    threads_posts: list[dict] = field(default_factory=list)


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
    """Parse Claude response into ContentDraft. Tries JSON first, falls back to text markers."""
    try:
        data = extract_json(raw)
        if isinstance(data, dict):
            return _map_json_content_draft(data)
    except (ValueError, TypeError):
        logger.debug("parse_content_draft: JSON failed, using legacy text parser")

    return _parse_content_draft_legacy(raw)


def _map_json_content_draft(data: dict) -> ContentDraft:
    draft = ContentDraft()
    draft.angle = humanize(data.get("angle", ""))
    draft.hook = humanize(data.get("hook", ""))
    draft.caption = humanize(data.get("caption", ""))
    draft.cta = humanize(data.get("cta", ""))
    draft.hashtags = humanize(data.get("hashtags", ""))
    draft.visual_prompt = data.get("visual_prompt", "")
    kw = data.get("stock_keywords", [])
    if isinstance(kw, list):
        draft.stock_keywords = [str(k).strip() for k in kw if str(k).strip()]
    elif isinstance(kw, str):
        draft.stock_keywords = [k.strip() for k in kw.split(",") if k.strip()]
    slides = data.get("slides", [])
    if isinstance(slides, list):
        draft.slides = [humanize(str(s)) for s in slides]
    # Threads series JSON: {"posts": [{"marker": "...", "text": "...", "why_it_works": "..."}]}
    posts = data.get("posts", [])
    if isinstance(posts, list) and posts:
        draft.threads_posts = [
            {
                "marker": humanize(str(p.get("marker", ""))),
                "text": _strip_series_meta(humanize(str(p.get("text", "")))),
                "why_it_works": humanize(str(p.get("why_it_works", ""))),
            }
            for p in posts
            if isinstance(p, dict) and p.get("text")
        ]
    return draft


def _parse_content_draft_legacy(raw: str) -> ContentDraft:
    """Legacy parser: extract fields from CAPTION:/CTA:/etc text markers."""
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
        elif probe.upper().startswith("STOCK_KEYWORDS:"):
            raw_kw = probe.split(":", 1)[1].strip()
            draft.stock_keywords = [k.strip() for k in raw_kw.split(",") if k.strip()]
            current_field = "stock_keywords"
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
            elif current_field == "stock_keywords":
                extra = [k.strip() for k in line.split(",") if k.strip()]
                draft.stock_keywords.extend(extra)
    return draft


_THREADS_SLOTS = [
    {"slot": "morning", "label": "УТРО", "marker": "УТРО"},
    {"slot": "day", "label": "ДЕНЬ", "marker": "ДЕНЬ"},
    {"slot": "evening", "label": "ВЕЧЕР", "marker": "ВЕЧЕР"},
]

_THREADS_DEFAULT_TIMES = {"morning": "09:00", "day": "13:00", "evening": "19:00"}

# ── Series templates for diverse Threads formats ─────────────────────────────
# Each template defines 3 slots with slot id, label, marker (for parsing), icon hint, and description.
SERIES_TEMPLATES = {
    "time_of_day": {
        "name": "Утро / День / Вечер",
        "slots": [
            {"slot": "morning", "label": "УТРО", "marker": "УТРО", "icon": "sunrise", "desc": "провокация, спорное мнение, байт на обсуждение"},
            {"slot": "day", "label": "ДЕНЬ", "marker": "ДЕНЬ", "icon": "sun", "desc": "конкретный совет, мясо, для сохранений"},
            {"slot": "evening", "label": "ВЕЧЕР", "marker": "ВЕЧЕР", "icon": "moon", "desc": "личная история, факап, рефлексия"},
        ],
        "default_times": {"morning": "09:00", "day": "13:00", "evening": "19:00"},
    },
    "myth_reality": {
        "name": "Миф / Реальность / Практика",
        "slots": [
            {"slot": "myth", "label": "МИФ", "marker": "МИФ", "icon": "x-circle", "desc": "распространённое заблуждение, которое цепляет и вызывает реакцию"},
            {"slot": "reality", "label": "РЕАЛЬНОСТЬ", "marker": "РЕАЛЬНОСТЬ", "icon": "check-circle", "desc": "как обстоят дела на самом деле, с фактами и примерами"},
            {"slot": "practice", "label": "ПРАКТИКА", "marker": "ПРАКТИКА", "icon": "hand", "desc": "что конкретно делать, применимый совет"},
        ],
        "default_times": {"myth": "09:00", "reality": "13:00", "practice": "19:00"},
    },
    "problem_solution": {
        "name": "Проблема / Разбор / Действие",
        "slots": [
            {"slot": "problem", "label": "ПРОБЛЕМА", "marker": "ПРОБЛЕМА", "icon": "alert-triangle", "desc": "конкретная боль аудитории, ситуация из жизни"},
            {"slot": "analysis", "label": "РАЗБОР", "marker": "РАЗБОР", "icon": "search", "desc": "почему это происходит, механизм, объяснение"},
            {"slot": "action", "label": "ДЕЙСТВИЕ", "marker": "ДЕЙСТВИЕ", "icon": "zap", "desc": "что делать прямо сейчас, одно конкретное действие"},
        ],
        "default_times": {"problem": "09:00", "analysis": "13:00", "action": "19:00"},
    },
    "story_arc": {
        "name": "Завязка / Поворот / Вывод",
        "slots": [
            {"slot": "setup", "label": "ЗАВЯЗКА", "marker": "ЗАВЯЗКА", "icon": "book-open", "desc": "сцена, история, ситуация — затянуть в рассказ"},
            {"slot": "twist", "label": "ПОВОРОТ", "marker": "ПОВОРОТ", "icon": "refresh-cw", "desc": "неожиданный поворот, инсайт, противоречие"},
            {"slot": "takeaway", "label": "ВЫВОД", "marker": "ВЫВОД", "icon": "lightbulb", "desc": "чему это учит, что можно забрать себе"},
        ],
        "default_times": {"setup": "09:00", "twist": "13:00", "takeaway": "19:00"},
    },
}

def pick_series_template() -> dict:
    """Randomly pick a series template for variety in Threads content."""
    import random
    return random.choice(list(SERIES_TEMPLATES.values()))


# ── AI expert: determine optimal post count for a topic ──────────────────────

_SERIES_SIZE_SYSTEM = """\
Ты — эксперт по контент-стратегии в Threads. Твоя задача — определить оптимальное \
количество постов в серии на один день для заданной темы.

Правила:
- Минимум 3, максимум 8 постов
- Простая тема (один совет, один факт) → 3 поста
- Средняя тема (несколько аспектов, история + практика) → 4-5 постов
- Глубокая тема (пошаговый гайд, разбор мифов, серия историй) → 6-8 постов
- Учитывай: каждый пост должен быть самодостаточным и ценным, не нужно раздувать ради количества
- Лучше 4 сильных поста, чем 6 с водой

Ответь ТОЛЬКО числом (3, 4, 5, 6, 7 или 8). Ничего больше."""

_SERIES_SIZE_PROMPT = """\
Тема серии: {topic}
Цель: {goal}
Формат: серия постов в Threads на один день

Сколько постов оптимально для раскрытия этой темы?"""


def determine_series_size_sync(topic: str, goal_key: str) -> int:
    """AI expert determines optimal number of posts (3-8) for a Threads series."""
    from bot.services.claude_client import call_claude

    goal_text = GOAL_GUIDANCE.get(goal_key, "Доверие")
    prompt = _SERIES_SIZE_PROMPT.format(topic=topic, goal=goal_text)
    try:
        raw = call_claude(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            system=_SERIES_SIZE_SYSTEM,
            context="series size expert",
        )
        count = int(raw.strip())
        return max(3, min(8, count))
    except (ValueError, TypeError):
        logger.debug("Series size expert returned non-numeric, defaulting to 3")
        return 3
    except Exception:
        logger.debug("Series size expert failed, defaulting to 3", exc_info=True)
        return 3


def build_dynamic_slots(post_count: int, template: dict) -> tuple[list[dict], dict]:
    """Build N slot definitions with evenly distributed times across 09:00-21:00.

    Uses the base template's first 3 slots as the narrative foundation,
    then generates additional numbered slots for posts 4+.

    Returns (slots, default_times).
    """
    base_slots = template["slots"]
    slots: list[dict] = []
    default_times: dict[str, str] = {}

    # Distribute times evenly across 09:00-21:00
    start_hour, end_hour = 9, 21
    interval = (end_hour - start_hour) / post_count

    for i in range(post_count):
        hour = int(start_hour + i * interval)
        minute = int((start_hour + i * interval - hour) * 60)
        time_str = f"{hour:02d}:{minute:02d}"

        if i < len(base_slots):
            slot = dict(base_slots[i])
            slot_id = slot["slot"]
        else:
            slot_id = f"post_{i + 1}"
            # Generate descriptive labels for extra slots
            extra_descs = [
                "развитие темы, углубление, новый аспект",
                "конкретный пример, кейс, история из практики",
                "неожиданный поворот, контринтуитивный факт",
                "практическое упражнение, чеклист, шаги",
                "обобщение, рефлексия, взгляд с другой стороны",
            ]
            desc = extra_descs[(i - len(base_slots)) % len(extra_descs)]
            slot = {
                "slot": slot_id,
                "label": f"ПОСТ {i + 1}",
                "marker": f"ПОСТ {i + 1}",
                "icon": "hash",
                "desc": desc,
            }

        slots.append(slot)
        default_times[slot["slot"]] = time_str

    return slots, default_times


_FORMAT_LABELS_RE = None


def _strip_series_meta(text: str) -> str:
    """Remove meta-headers that LLM sometimes leaks into post text.

    Examples removed:
      "Серия постов на Threads: Тема\\nПОСТ 1 (от тренда)\\n..."
      "THREADS: Серия постов (3-8 штук)\\nПОСТ 1..."
      "НОЧНАЯ АРОМАТЕРАПИЯ: СЕРИЯ ПОСТОВ\\nПОСТ 1 (ТРЕНД)\\n..."
    """
    import re
    # Remove leading lines that look like series headers or post numbering
    lines = text.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        # Skip meta-headers: "Серия постов...", "THREADS...", topic titles with "серия"
        if re.match(
            r"^(?:Серия постов|СЕРИЯ ПОСТОВ|THREADS|Threads)\b",
            stripped,
            re.IGNORECASE,
        ):
            continue
        # "ПОСТЫ НА THREADS", "POSTS FOR THREADS" etc.
        if re.search(r"\b(?:ПОСТЫ?|СЕРИЯ)\s+(?:НА\s+)?THREADS\b", stripped, re.IGNORECASE):
            continue
        # Lines containing "серия постов" anywhere (e.g. "ароматерапия: серия постов")
        if re.search(r"\bсерия\s+постов\b", stripped, re.IGNORECASE):
            continue
        # Lines that are just a topic title in ALL CAPS
        if re.match(r"^[А-ЯЁ\s,:\-]{10,}$", stripped) and "СЕРИЯ" in stripped.upper():
            continue
        # "ПОСТ 1 (от тренда)", "Пост 1️⃣"
        if re.match(r"^ПОСТ\s+\d", stripped, re.IGNORECASE):
            continue
        if re.match(r"^Пост\s+[\d️⃣]", stripped):
            continue
        if re.match(
            r"^(?:ПЕРВЫЙ|ВТОРОЙ|ТРЕТИЙ|ЧЕТВЁРТЫЙ|ПЯТЫЙ|ШЕСТОЙ|СЕДЬМОЙ|ВОСЬМОЙ)\s+ПОСТ\b",
            stripped,
            re.IGNORECASE,
        ):
            continue
        cleaned.append(line)
    result = "\n".join(cleaned).strip()
    # If we stripped everything, return empty
    if not result:
        return ""
    # If "ПОСТ 2" leaked into single-slot text, truncate at that boundary
    m = re.search(r"\n\s*(?:ПОСТ\s+[2-9]|Пост\s+[2-9️⃣])", result)
    if m:
        result = result[:m.start()].rstrip()
    # Strip trailing "Почему это сработает:" annotation (belongs in why_it_works field)
    result = re.sub(
        r"\n?\s*Почему это сработает\s*:.*$",
        "",
        result,
        flags=re.IGNORECASE | re.DOTALL,
    ).rstrip()
    return result


def _strip_format_labels(text: str) -> str:
    """Remove parenthetical format labels like (Hot Take) that leak from slot descriptions."""
    import re
    global _FORMAT_LABELS_RE
    if _FORMAT_LABELS_RE is None:
        _FORMAT_LABELS_RE = re.compile(
            r"\((?:Hot Take|Thread|Байт на обсуждение|Список|Туториал|Рефлексия|Шутка|Факап|Личная история)\)\s*",
            re.IGNORECASE,
        )
    return _FORMAT_LABELS_RE.sub("", text)


def _extract_why_it_works(text: str) -> tuple[str, str]:
    """Extract 'ПОЧЕМУ ЭТО СРАБОТАЕТ:' annotation from post text.

    Returns (cleaned_text, why_it_works).
    """
    import re

    match = re.search(
        r"\n?\s*(?:\*\*)?(?:ПОЧЕМУ ЭТО СРАБОТАЕТ|Почему это сработает)(?:\*\*)?[:\s]+(.+)",
        text,
    )
    if match:
        why = match.group(1).strip()
        cleaned = text[:match.start()].rstrip()
        return cleaned, why
    return text, ""


def _detect_template_from_caption(caption: str) -> dict:
    """Detect which series template was used based on markers in caption."""
    import re
    for tpl_key, tpl in SERIES_TEMPLATES.items():
        markers = [s["marker"] for s in tpl["slots"]]
        found = sum(1 for m in markers if re.search(rf"\b{re.escape(m)}\b", caption, re.IGNORECASE))
        if found >= 2:
            return tpl
    # Default to time_of_day
    return SERIES_TEMPLATES["time_of_day"]


def split_threads_posts(caption: str, template: dict | None = None) -> list[dict[str, str]]:
    """Split a threads caption into 3 posts using the detected or provided template."""
    import logging
    import re

    _logger = logging.getLogger(__name__)

    if template is None:
        template = _detect_template_from_caption(caption)

    slots_def = template["slots"]
    default_times = template.get("default_times", {})

    posts: list[dict[str, str]] = []
    markers = [s["marker"] for s in slots_def]
    # Expanded regex: handle emoji prefixes, numbering, hashtags, brackets
    pattern = "|".join(re.escape(m) for m in markers)
    parts = re.split(
        rf"(?:^|\n)\s*(?:[\U0001f300-\U0001faff\u2600-\u27bf]\s*)?(?:\d+[\.\)]\s*)?(?:#)?(?:\[)?(?:\*\*)?({pattern})(?:\*\*)?(?:\])?[:\s]*\n?",
        caption,
        flags=re.IGNORECASE,
    )

    slot_texts: dict[str, str] = {}
    slot_why: dict[str, str] = {}
    i = 1
    while i < len(parts) - 1:
        marker = parts[i].strip().upper()
        raw_text = parts[i + 1].strip()
        for s in slots_def:
            if s["marker"].upper() == marker:
                cleaned, why = _extract_why_it_works(raw_text)
                slot_texts[s["slot"]] = _strip_series_meta(_strip_format_labels(cleaned))
                slot_why[s["slot"]] = why
                break
        i += 2

    # Check: if only 1 slot has content but all text ended up there, redistribute
    filled_slots = [s["slot"] for s in slots_def if slot_texts.get(s["slot"])]
    if len(filled_slots) == 1 and len(slots_def) > 1:
        # All text merged into one slot — try to split it
        merged_text = slot_texts[filled_slots[0]]
        if len(merged_text) > 600:  # suspiciously long for a single post
            _logger.warning("split_threads_posts: all text in one slot (%d chars), redistributing", len(merged_text))
            sub_chunks = re.split(r"\n\s*\n", merged_text.strip())
            sub_chunks = [c.strip() for c in sub_chunks if len(c.strip()) > 20]
            if len(sub_chunks) >= len(slots_def):
                slot_texts.clear()
                slot_why.clear()
                for idx, slot_info in enumerate(slots_def):
                    if idx < len(sub_chunks):
                        cleaned, why = _extract_why_it_works(sub_chunks[idx])
                        slot_texts[slot_info["slot"]] = _strip_series_meta(_strip_format_labels(cleaned))
                        slot_why[slot_info["slot"]] = why

    # Fallback: if regex didn't find markers but text is non-empty, split by double newline
    has_content = any(slot_texts.get(s["slot"]) for s in slots_def)
    if not has_content and caption.strip():
        _logger.warning("split_threads_posts: markers not found, using double-newline fallback")
        chunks = re.split(r"\n\s*\n", caption.strip())
        chunks = [c.strip() for c in chunks if len(c.strip()) > 20]
        # If still not enough chunks, try single-newline split
        if len(chunks) < len(slots_def):
            chunks = re.split(r"\n", caption.strip())
            chunks = [c.strip() for c in chunks if len(c.strip()) > 20]
        for idx, slot_info in enumerate(slots_def):
            if idx < len(chunks):
                cleaned, why = _extract_why_it_works(chunks[idx])
                slot_texts[slot_info["slot"]] = _strip_series_meta(_strip_format_labels(cleaned))
                slot_why[slot_info["slot"]] = why

    for slot_info in slots_def:
        posts.append({
            "slot": slot_info["slot"],
            "label": slot_info["label"],
            "text": slot_texts.get(slot_info["slot"], ""),
            "default_time": default_times.get(slot_info["slot"], "12:00"),
            "why_it_works": slot_why.get(slot_info["slot"], ""),
            "icon": slot_info.get("icon", ""),
        })

    return posts


_THREADS_MAX_WORDS = 120


_THREADS_MAX_CHARS = 500


def _trim_thread_post_sync(text: str, topic: str) -> str:
    """If a threads post exceeds _THREADS_MAX_WORDS or 500 chars, ask Claude to shorten it."""
    word_count = len(text.split())
    if word_count <= _THREADS_MAX_WORDS and len(text) <= _THREADS_MAX_CHARS:
        return text
    prompt = (
        f"Сократи этот пост для Threads до СТРОГО 60-70 слов и НЕ БОЛЕЕ 500 символов. "
        f"Сохрани первую строку (хук) и основную мысль. Убери лишние детали. "
        f"Тема: {topic}\n\nТекст:\n{text}\n\n"
        f"Верни ТОЛЬКО сокращённый текст, ничего больше. Лимит: 500 символов."
    )
    result = _call_claude(prompt, max_tokens=400)
    trimmed = humanize(result.strip())
    if len(trimmed.split()) < word_count and len(trimmed) > 20:
        return trimmed
    return text


def trim_threads_posts(caption: str, topic: str) -> str:
    """Trim each УТРО/ДЕНЬ/ВЕЧЕР section if over word limit."""
    posts = split_threads_posts(caption)
    changed = False
    for post in posts:
        text = post.get("text", "")
        if not text:
            continue
        trimmed = _trim_thread_post_sync(text, topic)
        if trimmed != text:
            post["text"] = trimmed
            changed = True
    if not changed:
        return caption
    import re
    parts = []
    for post in posts:
        parts.append(f"{post['label']}")
        if post["text"]:
            parts.append(post["text"])
        if post.get("why_it_works"):
            parts.append(f"ПОЧЕМУ ЭТО СРАБОТАЕТ: {post['why_it_works']}")
        parts.append("")
    vp_match = re.search(r"VISUAL_PROMPT:\s*(.+)", caption)
    if vp_match:
        parts.append(f"VISUAL_PROMPT: {vp_match.group(1)}")
    return "\n".join(parts).strip()


def _strip_markdown_formatting(text: str) -> str:
    """Remove markdown formatting from social post text (headers, bold, blockquotes)."""
    import re
    # Remove headers (# ## ###)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    # Remove blockquote markers
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Remove code fences
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text.strip()


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


# ── Prompts (delegated to bot.agents.prompts.content_prompts) ────────────────

from bot.agents.prompts.content_prompts import (
    OUTPUT_FORMAT_DEFAULT as _OUTPUT_FORMAT_DEFAULT,  # noqa: F401
    OUTPUT_FORMAT_THREADS as _OUTPUT_FORMAT_THREADS,  # noqa: F401
    threads_output_format as _threads_output_format,
    topics_prompt as _topics_prompt_impl,
    custom_topics_prompt as _custom_topics_prompt_impl,
    strategist_prompt as _strategist_prompt_impl,
    suggest_topics_prompt as _suggest_topics_prompt_impl,
    writer_prompt as _writer_prompt_impl,
)


def _topics_prompt(trends_text: str, goal_key: str, format_key: str) -> str:
    return _topics_prompt_impl(trends_text, goal_key, format_key, GOAL_GUIDANCE, FORMAT_LABELS)


def _custom_topics_prompt(user_brief: str, goal_key: str, format_key: str) -> str:
    return _custom_topics_prompt_impl(user_brief, goal_key, format_key, GOAL_GUIDANCE, FORMAT_LABELS)


def _strategist_prompt(topic: str, goal_key: str, format_key: str, blend_context: dict | None = None, rag_context: str = "", practice_focus: str = "aroma") -> str:
    return _strategist_prompt_impl(topic, goal_key, format_key, GOAL_GUIDANCE, FORMAT_LABELS, blend_context=blend_context, rag_context=rag_context, practice_focus=practice_focus)


def _writer_prompt(topic: str, goal_key: str, format_key: str, angle: str, hook: str, blend_context: dict | None = None, rag_context: str = "", practice_focus: str = "aroma", series_template: dict | None = None) -> str:
    return _writer_prompt_impl(topic, goal_key, format_key, angle, hook, GOAL_GUIDANCE, blend_context=blend_context, rag_context=rag_context, practice_focus=practice_focus, series_template=series_template)


# ── Agent functions ──────────────────────────────────────────────────────────

def _call_claude(prompt: str, max_tokens: int, system: str = "") -> str:
    from bot.services.claude_client import call_claude

    return call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        system=system,
        context="content agent",
    )



def _suggest_topics_prompt(goal_key: str, format_key: str, exclude_topics: list[str]) -> str:
    return _suggest_topics_prompt_impl(goal_key, format_key, exclude_topics, GOAL_GUIDANCE, FORMAT_LABELS)


def _suggest_topics_sync(goal_key: str, format_key: str, exclude_topics: list[str]) -> list[str]:
    prompt = _suggest_topics_prompt(goal_key, format_key, exclude_topics)
    raw = _call_claude(prompt, max_tokens=500)
    return parse_numbered_list(raw, limit=5)


def _generate_topics_sync(
    results: list[SourceResult] | None,
    goal_key: str,
    format_key: str,
    user_brief: str = "",
) -> list[str]:
    from cache.store import cache
    cache_key = f"topics:content:{format_key}:{goal_key}"
    if user_brief:
        prompt = _custom_topics_prompt(user_brief, goal_key, format_key)
    else:
        trends_text = _format_trends(results or [])
        prompt = _topics_prompt(trends_text, goal_key, format_key)
    try:
        raw = _call_claude(prompt, max_tokens=900)
        topics = parse_numbered_list(raw, limit=10)
        if topics:
            cache.set(cache_key, topics)
        return topics
    except Exception:
        logger.warning("_generate_topics_sync failed, trying cache", exc_info=True)
        return cache.get(cache_key) or []


def _generate_strategist_sync(topic: str, goal_key: str, format_key: str, blend_context: dict | None = None, rag_context: str = "", practice_focus: str = "aroma") -> tuple[str, str]:
    """Step 1: Strategist finds creative angle and hook line."""
    # Enrich with performance feedback from past publications
    enriched_rag = rag_context
    try:
        import asyncio
        from bot.services.content_analytics import build_strategist_feedback_text
        loop = asyncio.new_event_loop()
        feedback_text = loop.run_until_complete(build_strategist_feedback_text())
        loop.close()
        if feedback_text:
            enriched_rag = (enriched_rag + "\n" + feedback_text) if enriched_rag else feedback_text
    except Exception:
        logger.debug("Failed to load strategist feedback", exc_info=True)

    raw = _call_claude(_strategist_prompt(topic, goal_key, format_key, blend_context=blend_context, rag_context=enriched_rag, practice_focus=practice_focus), max_tokens=250)
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
    topic: str, goal_key: str, format_key: str, angle: str, hook: str, blend_context: dict | None = None, rag_context: str = "", practice_focus: str = "aroma"
) -> ContentDraft:
    """Step 2: Writer produces platform-native draft. Step 3: Editor polishes."""
    from bot.agents.creative_team import edit_post_sync

    # Pick a random series template and determine post count for threads_series
    series_template = None
    series_template_key = ""
    if format_key == "threads_series":
        import random
        series_template_key = random.choice(list(SERIES_TEMPLATES.keys()))
        base_template = SERIES_TEMPLATES[series_template_key]
        # AI expert determines optimal post count for the topic
        post_count = determine_series_size_sync(topic, goal_key)
        dynamic_slots, dynamic_times = build_dynamic_slots(post_count, base_template)
        series_template = {
            "name": base_template["name"],
            "slots": dynamic_slots,
            "default_times": dynamic_times,
            "post_count": post_count,
        }

    token_limit = max(900, 300 * (series_template["post_count"] if series_template else 3))
    raw = _call_claude(
        _writer_prompt(topic, goal_key, format_key, angle, hook, blend_context=blend_context, rag_context=rag_context, practice_focus=practice_focus, series_template=series_template), max_tokens=token_limit
    )
    draft = parse_content_draft(raw)
    draft.angle = angle
    draft.series_template_key = series_template_key
    if not draft.hook:
        draft.hook = hook

    if not _has_structured_content(draft) and raw.strip():
        draft.caption = humanize(raw.strip())

    # Threads series: JSON parsed into threads_posts directly.
    # Legacy fallback: if JSON parsing failed, caption holds raw text with markers.
    if format_key == "threads_series":
        if not draft.threads_posts and not draft.caption and raw.strip():
            draft.caption = raw.strip()
        # Strip markdown from individual post texts
        if draft.threads_posts:
            for p in draft.threads_posts:
                p["text"] = _strip_markdown_formatting(p["text"])
        # Store template info for downstream use
        if series_template:
            draft._series_template = series_template

    # Strip markdown formatting from caption (forbidden in social posts)
    if draft.caption:
        draft.caption = _strip_markdown_formatting(draft.caption)

    # Step 3: Editor pass (skip for threads_series with structured posts — edit each post individually)
    if format_key == "threads_series" and draft.threads_posts:
        for p in draft.threads_posts:
            if p.get("text"):
                p["text"] = edit_post_sync(p["text"], topic, platform=format_key)
    elif draft.caption:
        pre_edit = draft.caption
        draft.caption = edit_post_sync(draft.caption, topic, platform=format_key)
        # If editor destroyed threads markers, fall back to pre-edit caption
        if format_key == "threads_series":
            check_posts = split_threads_posts(draft.caption)
            if not any(p.get("text") for p in check_posts):
                draft.caption = pre_edit

    # Step 4: Quality evaluation with retry
    from bot.agents.quality_evaluator import _evaluate_sync
    score = None
    # For threads_series with structured posts, evaluate concatenated text
    eval_text = draft.caption
    if format_key == "threads_series" and draft.threads_posts:
        eval_text = "\n\n".join(p["text"] for p in draft.threads_posts if p.get("text"))
    for attempt in range(_MAX_QUALITY_RETRIES):
        if not eval_text:
            break
        score = _evaluate_sync(eval_text, format_key, topic)
        if score["passed"]:
            break
        if attempt < _MAX_QUALITY_RETRIES - 1:
            critique_prompt = (
                f"{_writer_prompt(topic, goal_key, format_key, angle, hook, blend_context=blend_context, rag_context=rag_context)}\n\n"
                f"Предыдущая версия получила низкую оценку. Критика редактора:\n"
                f"{score['critique']}\n\n"
                f"Перепиши текст учитывая это замечание. "
                f"Сохрани угол и хук, но улучши то, что указано в критике."
            )
            raw2 = _call_claude(critique_prompt, max_tokens=token_limit)
            draft2 = parse_content_draft(raw2)
            if format_key == "threads_series" and draft2.threads_posts:
                for p in draft2.threads_posts:
                    if p.get("text"):
                        p["text"] = edit_post_sync(p["text"], topic, platform=format_key)
                draft2.angle = angle
                draft2.hook = hook
                draft = draft2
                eval_text = "\n\n".join(p["text"] for p in draft.threads_posts if p.get("text"))
            elif draft2.caption:
                pre_edit2 = draft2.caption
                draft2.caption = edit_post_sync(draft2.caption, topic, platform=format_key)
                if format_key == "threads_series":
                    check2 = split_threads_posts(draft2.caption)
                    if not any(p.get("text") for p in check2):
                        draft2.caption = pre_edit2
                draft2.angle = angle
                draft2.hook = hook
                draft = draft2

    if score is not None:
        draft.quality_score = dict(score)

    return draft


def _generate_draft_sync(topic: str, goal_key: str, format_key: str, blend_context: dict | None = None, rag_context: str = "", practice_focus: str = "aroma") -> ContentDraft:
    """Full 3-agent chain: Strategist → Writer → Editor."""
    angle, hook = _generate_strategist_sync(topic, goal_key, format_key, blend_context=blend_context, rag_context=rag_context, practice_focus=practice_focus)
    return _generate_writer_sync(topic, goal_key, format_key, angle, hook, blend_context=blend_context, rag_context=rag_context, practice_focus=practice_focus)


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




async def suggest_topics(goal_key: str, format_key: str, exclude_topics: list[str]) -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor, _suggest_topics_sync, goal_key, format_key, exclude_topics
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


async def generate_content_draft(topic: str, goal_key: str, format_key: str, blend_context: dict | None = None, rag_context: str = "", practice_focus: str = "aroma") -> ContentDraft:
    """Full 3-agent chain as a single async call."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _generate_draft_sync, topic, goal_key, format_key, blend_context, rag_context, practice_focus)


def generate_image_bytes(prompt: str) -> bytes | None:
    return generate_gemini_image_sync(prompt, log_context="Gemini content image").image_bytes
