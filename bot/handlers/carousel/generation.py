"""Carousel content generation: drafts, image prompts, QA, slide regen."""
from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bot.services.gemini_images import generate_gemini_image_sync
from config import settings
from bot.handlers.threads import _fix_dashes

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)
_img_executor = ThreadPoolExecutor(max_workers=5)

# ── Font ────────────────────────────────────────────────────────────────────
_FONT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts" / "DeldedaOpen.ttf"
_FONT_NAME = "Deledda Open"

# ── Layout constants ────────────────────────────────────────────────────────
_SLIDE_EMU = 1080 * 9525

_DEFAULT_FORBIDDEN_VISUAL_MOTIFS = [
    "hands joined together",
    "prayer pose",
    "praying hands",
    "cult ritual circle",
    "sect-like worship",
    "two cupped hands around one object",
]

# Slide narrative roles — used for regen-slide context.
# These are templates; actual count is determined by Content Factory.
_ROLE_POOL = [
    ("hook", "Hook", "hook — powerful first image that stops scrolling"),
    ("problem", "Проблема", "problem — a relatable moment of stress, overload, or disconnection"),
    ("mechanism", "Механизм", "mechanism — body process shown metaphorically, a transitional mood"),
    ("insight", "Инсайт", "insight — moment of clarity, first hint of the brand world"),
    ("solution", "Решение", "solution — the sensory practice, the remedy in action"),
    ("cta", "CTA", "call to action — warm human invitation"),
]


def get_slide_roles(total: int) -> list[str]:
    """Return role keys for *total* slides. First is always hook, last is always cta."""
    if total <= 0:
        return []
    if total == 1:
        return ["hook"]
    roles = ["hook"]
    # Middle roles cycle through pool (skipping hook/cta)
    middle_pool = [r[0] for r in _ROLE_POOL[1:-1]]
    for i in range(total - 2):
        roles.append(middle_pool[i % len(middle_pool)])
    roles.append("cta")
    return roles


def get_slide_visual_role(index: int, total: int) -> str:
    """Return visual role description for slide at index."""
    roles = get_slide_roles(total)
    if index < len(roles):
        role_key = roles[index]
        for key, _, desc in _ROLE_POOL:
            if key == role_key:
                return desc
    return f"supporting slide {index + 1}"


def get_slide_label(index: int, total: int) -> str:
    """Return human-readable label for slide at index."""
    roles = get_slide_roles(total)
    if index < len(roles):
        role_key = roles[index]
        for key, label, _ in _ROLE_POOL:
            if key == role_key:
                return f"Слайд {index + 1} — {label}"
    return f"Слайд {index + 1}"

# ── Prompts ─────────────────────────────────────────────────────────────────
_PROMPT_CAROUSEL = """\
Ты — сценарист карусели для Instagram. Ниша: регуляция нервной системы через \
сенсорные практики (ароматерапия, медитации, гонг).
Создай черновик карусели по теме: {topic}

Определи оптимальное количество слайдов (от 4 до 10) исходя из глубины темы. \
Не добавляй слайды ради количества — каждый должен нести новую мысль.

Требования:
- Описывай только реалистичные повседневные ситуации. Все детали одного слайда должны быть логически связаны и физически возможны
- Первый слайд: цепляющий хук, до 60 символов
- Средние слайды: один тезис + 1-2 предложения, до 120 символов на слайд
- Последний слайд: призыв к действию, до 80 символов
- Живой язык, от первого лица, без клише и длинных тире
- Базовый промпт для фото (английский, 15-25 слов): сцена, палитра из темы, освещение, композиция. Без параметров Midjourney.

Формат — строго:
SLIDE1: [текст]
SLIDE2: [текст]
...
SLIDE{{N}}: [текст]
IMG_PROMPT: [промпт]
"""

_PROMPT_TOPICS = """\
Ты — стратег по контенту в Instagram. Ниша: регуляция нервной системы через \
сенсорные практики (ароматерапия, медитации, гонг).

На основе трендов ниже предложи 10 тем для карусели. \
Каждая тема — конкретный угол, ситуация или вопрос. Без воды и банальностей.

Формат — строго нумерованный список:
1. [тема]
...
10. [тема]
"""

_FALLBACK_IMG_PROMPT = (
    "terracotta minimal lifestyle, incense smoke, soft natural light, "
    "--ar 4:5 --style atmospheric"
)


# ── Claude helpers ──────────────────────────────────────────────────────────

def _claude_topics_carousel(trends_text: str) -> list[str]:
    from bot.services.claude_client import call_claude
    from cache.store import cache
    try:
        text = call_claude(
            messages=[{"role": "user", "content": f"Тренды:\n{trends_text}"}],
            max_tokens=800,
            system=_PROMPT_TOPICS,
            context="carousel topics",
        )
        topics: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if line and line[0].isdigit() and ". " in line:
                topics.append(line.split(". ", 1)[1].strip())
        topics = topics[:10]
        if topics:
            cache.set("topics:carousel", topics)
        return topics
    except Exception:
        logger.warning("_claude_topics_carousel failed, trying cache", exc_info=True)
        return cache.get("topics:carousel") or []


def _claude_carousel_draft(topic: str, angle: str = "", hook: str = "") -> tuple[list[str], str]:
    from bot.agents.carousel_editor import _parse_slides
    from bot.services.claude_client import call_claude
    user_content = _PROMPT_CAROUSEL.format(topic=topic)
    if angle or hook:
        user_content += f"\n\nСтратег предложил:\nУгол: {angle}\nХук: {hook}\nИспользуй этот угол и хук как основу."
    text = call_claude(
        messages=[{"role": "user", "content": user_content}],
        max_tokens=900,
        context="carousel draft",
    )
    slides = [_fix_dashes(s) for s in _parse_slides(text)]
    img_prompt = ""
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("IMG_PROMPT:"):
            img_prompt = line.split(":", 1)[1].strip()
            break
    return slides, img_prompt


def _forbidden_visual_motifs() -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for motif in [*_DEFAULT_FORBIDDEN_VISUAL_MOTIFS, *getattr(settings, "carousel_forbidden_visual_motifs_list", [])]:
        value = str(motif).strip()
        lowered = value.lower()
        if not value or lowered in seen:
            continue
        seen.add(lowered)
        result.append(value)
    return result


def _forbidden_visual_motifs_text() -> str:
    return ", ".join(_forbidden_visual_motifs())


def _generate_slide_image_prompts_sync(slides: list[str], topic: str, blend_context: dict | None = None) -> list[str]:
    """Generate one unique, detailed image prompt per slide via art-director + image prompt router.

    Step 1: Claude as art director produces short 30-50 word prompts per slide.
    Step 2: Each prompt is expanded by the image prompt router (model-aware).
    """
    from bot.agents.image_prompt_router import optimize_image_prompt
    from bot.services.claude_client import call_claude

    slides_desc = "\n".join(
        f"Slide {i + 1}: {s if isinstance(s, str) else ' '.join(str(x) for x in s)}"
        for i, s in enumerate(slides)
    )

    blend_visual = ""
    if blend_context:
        from bot.agents.blend_content_context import mood_to_visual_directive
        visual_directive = mood_to_visual_directive(blend_context.get("profile", {}))
        oil_names_en = [o.get("name_en", "") for o in blend_context.get("oils", []) if o.get("name_en")]
        if visual_directive:
            blend_visual = f"\nBlend visual mood: {visual_directive}\n"
        if oil_names_en:
            blend_visual += f"Featured botanicals: {', '.join(oil_names_en)}\n"

    prompt = (
        f'You are an art director for an Instagram carousel on the topic: "{topic}"\n\n'
        f"{blend_visual}"
        "Step 1: Determine the ideal color palette, mood, and lighting from the topic.\n"
        "The palette must match the emotional tone of the topic. Examples:\n"
        "- 'кайф от кабриолета' → bright sun, azure sky, warm golden light, vivid saturated colors\n"
        "- 'заземление через аромат' → earth tones, terracotta, sage, warm wood\n"
        "- 'зимний уют' → deep amber, warm burgundy, soft candlelight glow\n\n"
        "Step 2: Determine each slide's narrative role based on its position in the carousel.\n\n"
        "Step 3: Generate one image prompt per slide. Each must:\n"
        "- Be 30-50 words in English\n"
        "- Describe the scene, palette (from your Step 1 analysis), lighting, and composition\n"
        "- Be visually distinct from other slides\n"
        "- NOT use any Midjourney parameters (no --ar, --style, --v, --no)\n\n"
        "Universal constraints:\n"
        "- Color intensity: rich, saturated tones matching topic mood. Never grey/washed-out.\n"
        "- Forbidden everywhere: stock photo look, plastic, harsh shadows, "
        "white/grey plain backgrounds, human faces, any text or typography\n"
        f"- Also forbidden everywhere: {_forbidden_visual_motifs_text()}\n"
        "- Required: leave a large clear area (at least 1/3 of frame) for text overlay\n\n"
        f"{slides_desc}\n\n"
        "Return strictly in this format, nothing else:\n"
        + "\n".join(f"IMG{i + 1}: [prompt]" for i in range(len(slides)))
    )

    raw_text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        context="carousel image prompts",
    )

    parsed: dict[int, str] = {}
    for line in raw_text.splitlines():
        line = line.strip()
        for i in range(1, len(slides) + 1):
            if line.startswith(f"IMG{i}:"):
                parsed[i - 1] = line.split(":", 1)[1].strip()
                break

    raw_prompts: list[str] = []
    for i, slide in enumerate(slides):
        if i in parsed:
            raw_prompts.append(parsed[i])
        else:
            raw_prompts.append(
                f"vibrant lifestyle scene matching '{topic}', {slide[:35]}, "
                f"rich saturated colors, natural light"
            )

    # Expand each raw prompt through the image prompt router
    from bot.services.carousel_assets import _get_carousel_model
    blend_mood = ""
    if blend_context:
        from bot.agents.blend_content_context import mood_to_visual_directive as _m2v
        blend_mood = _m2v(blend_context.get("profile", {}))

    model = _get_carousel_model()
    optimized: list[str] = []
    for i, raw in enumerate(raw_prompts):
        try:
            expanded = optimize_image_prompt(
                raw, model=model, topic=topic, slide_number=i, total_slides=len(slides),
                blend_mood=blend_mood or None,
            )
            optimized.append(expanded)
        except Exception:
            logger.exception("Image prompt router failed for slide %d", i + 1)
            optimized.append(raw)
    return optimized


def _generate_carousel_sync(topic: str, user_forbidden: list[str] | None = None, blend_context: dict | None = None, render_style: str = "overlay") -> tuple[list[str], list[str], str, str]:
    """Draft -> editor -> refined slides + per-slide image prompts.

    Returns (slides, img_prompts, angle, hook).
    """
    from bot.agents.carousel_editor import edit_carousel_sync
    import time

    from bot.agents.content import _generate_strategist_sync
    angle, hook = _generate_strategist_sync(topic, goal_key="trust", format_key="carousel", blend_context=blend_context)

    for attempt in range(2):
        try:
            raw_slides, _ = _claude_carousel_draft(topic, angle, hook)
            if not raw_slides:
                logger.warning("_claude_carousel_draft empty on attempt %d, topic: %s", attempt + 1, topic)
                if attempt == 0:
                    time.sleep(3)
                    continue
                return [], [], angle, hook
            refined = edit_carousel_sync(raw_slides, topic, user_forbidden=user_forbidden or [])
            if not refined:
                logger.warning("edit_carousel_sync empty on attempt %d, topic: %s", attempt + 1, topic)
                if attempt == 0:
                    time.sleep(3)
                    continue
                return [], [], angle, hook
            img_prompts = _generate_slide_image_prompts_sync(refined, topic, blend_context=blend_context)
            # Apply editorial prompt modifier if render_style is editorial
            if render_style == "editorial":
                from bot.agents.carousel_editorial import editorial_image_prompt_modifier
                img_prompts = [editorial_image_prompt_modifier(p) for p in img_prompts]
            return refined, img_prompts, angle, hook
        except Exception:
            logger.exception("_generate_carousel_sync attempt %d failed for topic: %s", attempt + 1, topic)
            if attempt == 0:
                time.sleep(3)
                continue
    return [], [], angle, hook


# ── Shared text wrapping ──────────────────────────────────────────────────

def wrap_slide_text(text: str, max_chars_per_line: int = 30) -> list[str]:
    """Word-wrap slide text to a target character width.

    Used by both preview PNG and PPTX to ensure consistent line breaks.
    """
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) <= max_chars_per_line:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ── Image analysis ──────────────────────────────────────────────────────────

def _find_text_zone(img_bytes: bytes, preferred_zone: str | None = None) -> tuple[float, float]:
    """Return (top_fraction, height_fraction) for text box placement.

    Uses a 3×5 grid (3 columns × 5 rows) to find the quietest block with
    enough space for text overlay. Each cell is scored by variance (low = calm)
    and brightness (low = dark → white text readable).

    If *preferred_zone* is given, adds a distance penalty so the algorithm
    is biased towards the preferred vertical region.
    """
    _ZONE_CENTERS = {"top": 0.5, "center": 2, "bottom": 3.5, "bottom-center": 3}

    try:
        from PIL import Image as _PIL, ImageStat, ImageFilter
        img = _PIL.open(io.BytesIO(img_bytes)).convert("L").resize((90, 90))
        img = img.filter(ImageFilter.GaussianBlur(2))
        W, H = img.size  # 90, 90
        cols, rows = 3, 5
        cw, rh = W // cols, H // rows

        zone_center = _ZONE_CENTERS.get(preferred_zone) if preferred_zone else None

        best_score = float("inf")
        best_row, best_col = 3, 0  # safe default: bottom-left

        for r in range(rows):
            for c in range(cols):
                block = img.crop((c * cw, r * rh, (c + 1) * cw, (r + 1) * rh))
                stat = ImageStat.Stat(block)
                avg = stat.mean[0]
                std = stat.stddev[0]
                # Lower score = better: prefer calm (low std) and dark (low avg)
                score = std * 1.5 + avg * 0.4
                # Bias towards preferred zone when specified
                if zone_center is not None:
                    score += abs(r - zone_center) * 25
                if score < best_score:
                    best_score = score
                    best_row, best_col = r, c

        # Text zone spans full width at the best row
        top_frac = best_row / rows + 0.01
        h_frac = 1 / rows + 0.04
        if top_frac + h_frac > 0.97:
            top_frac = 0.97 - h_frac
        return top_frac, h_frac
    except Exception:
        return 0.63, 0.32  # safe default: lower third


def _apply_note_to_prompt(prompt: str, note: str) -> str:
    """Combine prompt and user note."""
    base = prompt.strip().rstrip(",")
    return f"{base}, {note.strip()}" if note.strip() else base


def _qa_image_sync(
    img_bytes: bytes, prompt: str, note: str = "", slide_idx: int = -1
) -> tuple[bool, str]:
    """Vision QA: check for hallucinations, forbidden elements, note compliance."""
    from bot.services.claude_client import call_claude
    import base64

    note_check = (
        f"\n4. The user requested: \"{note}\" -- verify this is clearly reflected."
        if note else ""
    )
    qa_prompt = (
        f"You are a strict visual QA agent for Instagram carousel images.\n"
        f"Image prompt used: {prompt}\n\n"
        f"Check this image for issues:\n"
        f"1. Physically impossible or hallucinated elements "
        f"(e.g. lavender on fire, smoke from cold objects, impossible anatomy of objects)\n"
        f"2. Any visible text, watermarks, logos, or typography"
        f"\n2b. Any forbidden visual motifs such as: {_forbidden_visual_motifs_text()}"
        f"{note_check}\n\n"
        f"Reply in this exact format (2 lines only):\n"
        f"PASS or FAIL\n"
        f"REASON: [one short sentence. If PASS write: OK]"
    )
    try:
        text = call_claude(
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64.standard_b64encode(img_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": qa_prompt},
                ],
            }],
            max_tokens=80,
            context="carousel qa image",
        )
        passed = text.upper().startswith("PASS")
        reason = ""
        for line in text.splitlines():
            if line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()
                break
        return passed, reason
    except Exception as exc:
        logger.warning("QA vision error: %s", exc)
        return True, ""  # Don't block on QA errors


# ── Gemini ──────────────────────────────────────────────────────────────────

def _gemini_slide(prompt: str, key_index: int = 0) -> bytes | None:
    return generate_gemini_image_sync(prompt, log_context="Gemini carousel").image_bytes


def _regen_slide_text_sync(topic: str, slides: list[str], idx: int) -> str:
    """Ask Claude to rewrite a single slide, aware of its role and neighbours."""
    from bot.services.claude_client import call_claude
    total = len(slides)
    role = get_slide_visual_role(idx, total)
    label = get_slide_label(idx, total)
    others = "\n".join(
        f"Слайд {i + 1}: {s}" for i, s in enumerate(slides) if i != idx
    )
    prompt = (
        f"Ты — копирайтер карусели для Instagram. Ниша: регуляция нервной системы через сенсорные практики.\n\n"
        f"Тема карусели: {topic}\n"
        f"Роль {label}: {role}\n\n"
        f"Другие слайды (контекст):\n{others}\n\n"
        f"Напиши новый вариант текста для {label}.\n"
        f"Требования: максимум 5-6 строк, до 10 слов в строке, живой язык, без клише, без длинных тире.\n"
        f"Верни только текст слайда — ничего больше."
    )
    text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        context="carousel regen slide",
    )
    return _fix_dashes(text)
