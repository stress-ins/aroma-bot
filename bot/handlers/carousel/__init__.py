"""Carousel handler package — backward-compatible re-exports.

All public and private names that were previously importable from
``bot.handlers.carousel`` are re-exported here so that existing code
continues to work unchanged.
"""
from __future__ import annotations

from config import settings  # noqa: F401 — tests monkeypatch this on the module

# ── generation.py ────────────────────────────────────────────────────────────
from bot.handlers.carousel.generation import (  # noqa: F401
    _executor,
    _img_executor,
    _FONT_PATH,
    _FONT_NAME,
    _SLIDE_EMU,
    _DEFAULT_FORBIDDEN_VISUAL_MOTIFS,
    _ROLE_POOL,
    get_slide_roles,
    get_slide_visual_role,
    get_slide_label,
    _PROMPT_CAROUSEL,
    _PROMPT_TOPICS,
    _FALLBACK_IMG_PROMPT,
    _claude_topics_carousel,
    _claude_carousel_draft,
    _forbidden_visual_motifs,
    _forbidden_visual_motifs_text,
    _generate_slide_image_prompts_sync,
    _generate_carousel_sync,
    _find_text_zone,
    _apply_note_to_prompt,
    _qa_image_sync,
    _gemini_slide,
    _regen_slide_text_sync,
)

# ── pptx.py ──────────────────────────────────────────────────────────────────
from bot.handlers.carousel.pptx import (  # noqa: F401
    _embed_font_in_pptx,
    _build_pptx,
)

# ── formatters.py ────────────────────────────────────────────────────────────
from bot.handlers.carousel.formatters import (  # noqa: F401
    _make_slide_prompts_with_text,
    _make_slide_prompts_no_text,
    _format_for_canva,
)

# ── keyboards.py ─────────────────────────────────────────────────────────────
from bot.handlers.carousel.keyboards import (  # noqa: F401
    _source_keyboard,
    _topics_keyboard,
    _action_buttons_no_images,
    _canva_buttons,
    _pptx_from_my_images_button,
    _text_review_keyboard,
    _persist_carousel_draft,
    _review_keyboard,
    _slide_actions_keyboard,
)

# ── handlers.py ──────────────────────────────────────────────────────────────
from bot.handlers.carousel.handlers import (  # noqa: F401
    _show_slide_for_edit,
    _run_image_generation,
    _run_carousel,
    cmd_carousel,
    cb_carousel,
    msg_carousel_topic,
    msg_carousel_photo,
    build_carousel_handler,
)
