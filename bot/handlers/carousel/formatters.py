"""Text formatting helpers for carousel output."""
from __future__ import annotations

import html as _html

from bot.handlers.carousel.generation import _SLIDE_LABELS


def _make_slide_prompts_with_text(img_prompts: list[str], slides: list[str]) -> str:
    """HTML-formatted — send with parse_mode=HTML.
    Each slide gets its own unique image prompt with text overlay injected.
    """
    lines = ["<b>🍌 Nana Banana — с текстом (1080×1350, --ar 4:5):</b>\n"]
    flags = "--ar 4:5 --style atmospheric"
    for i, (prompt, slide) in enumerate(zip(img_prompts, slides), 1):
        # Strip trailing flags, inject text overlay, re-add flags
        clean = prompt.replace(flags, "").strip().rstrip(",").rstrip()
        full_prompt = f'{clean}, text overlay: "{slide[:50]}", {flags}'
        lines.append(
            f"<b>Слайд {i}:</b>\n"
            f"<pre>{_html.escape(full_prompt)}</pre>"
        )
    return "\n".join(lines)


def _make_slide_prompts_no_text(img_prompts: list[str], slides: list[str]) -> str:
    """HTML-formatted — send with parse_mode=HTML.
    Each slide gets its own unique image prompt (backgrounds, no text).
    """
    lines = ["<b>🍌 Nana Banana — фон без текста (1080×1350, --ar 4:5):</b>\n"]
    for i, (prompt, slide) in enumerate(zip(img_prompts, slides), 1):
        lines.append(
            f"<b>Слайд {i}</b> — {_html.escape(slide[:45])}\n"
            f"<pre>{_html.escape(prompt)}</pre>"
        )
    return "\n".join(lines)


def _format_for_canva(slides: list[str]) -> str:
    """HTML-formatted — send with parse_mode=HTML."""
    parts = ["<b>📋 Тексты для Canva:</b>\n"]
    for i, slide in enumerate(slides):
        label = _SLIDE_LABELS[i] if i < len(_SLIDE_LABELS) else f"Слайд {i + 1}"
        parts.append(f"<b>{_html.escape(label)}</b>\n<pre>{_html.escape(slide)}</pre>")
    parts.append(
        "\n💡 Используй фоны из Nana Banana (без текста), "
        "добавляй текст в Canva из Brand Kit."
    )
    return "\n\n".join(parts)
