"""Inline keyboard builders for carousel flow."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.handlers.carousel.generation import get_slide_label

logger = logging.getLogger(__name__)


def _source_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📈 На основе трендов", callback_data="ca:source:trends"),
        InlineKeyboardButton("✏️ Своя тема",          callback_data="ca:source:custom"),
    ]])


def _topics_keyboard(topics: list[str]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(str(i + 1), callback_data=f"ca:g:{i}") for i in range(len(topics))]
    buttons = [row[i:i + 5] for i in range(0, len(row), 5)]
    buttons.append([InlineKeyboardButton("🔄 Обновить темы", callback_data="ca:source:trends")])
    return InlineKeyboardMarkup(buttons)


def _action_buttons_no_images() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍌 Nana Banana (без текста)", callback_data="ca:prompt:notxt"),
            InlineKeyboardButton("🍌 Nana Banana (с текстом)",  callback_data="ca:prompt:text"),
        ],
        [
            InlineKeyboardButton("📄 PPTX (только тексты)", callback_data="ca:pptx:noimg"),
            InlineKeyboardButton("📋 Тексты для Canva",     callback_data="ca:prompt:canva"),
        ],
    ])


def _canva_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Тексты для Canva", callback_data="ca:prompt:canva"),
    ]])


def _pptx_from_my_images_button(count: int, total: int = 6) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"📄 Собрать PPTX ({count}/{total} картинок)",
            callback_data="ca:pptx:userimages",
        )
    ]])


def _text_review_keyboard(n_slides: int) -> InlineKeyboardMarkup:
    """Keyboard for text-only review stage (before image generation)."""
    row = [InlineKeyboardButton(str(i + 1), callback_data=f"ca:edit:{i}") for i in range(n_slides)]
    buttons = [row[i:i + 5] for i in range(0, len(row), 5)]
    buttons.append([
        InlineKeyboardButton("🖼 Генерировать картинки", callback_data="ca:gen:images"),
        InlineKeyboardButton("🔄 Пересоздать",           callback_data="ca:regen:all"),
    ])
    buttons.append([
        InlineKeyboardButton("🍌 Промпты (с текстом)",  callback_data="ca:prompt:text"),
        InlineKeyboardButton("🍌 Промпты (фон)",        callback_data="ca:prompt:notxt"),
    ])
    return InlineKeyboardMarkup(buttons)


def _persist_carousel_draft(
    context: ContextTypes.DEFAULT_TYPE,
    topic: str,
    slides: list[str],
    img_prompts: list[str],
    angle: str = "",
    hook: str = "",
) -> str | None:
    from bot.services.drafts_store import save_draft as _save_draft, update_draft as _update_draft

    payload = {"slides": slides, "img_prompts": img_prompts}
    if hook:
        payload["hook"] = hook
    if angle:
        payload["angle"] = angle
    existing_draft_id = str(context.user_data.get("ca_draft_id", "")).strip()
    if existing_draft_id:
        updated = _update_draft(existing_draft_id, topic=topic, status="draft", payload=payload)
        if updated:
            context.user_data["ca_draft_id"] = updated.draft_id
            return updated.draft_id

    saved = _save_draft(
        kind="carousel",
        topic=topic,
        source="/carousel",
        payload=payload,
    )
    context.user_data["ca_draft_id"] = saved.draft_id
    return saved.draft_id


def _review_keyboard(n_slides: int, has_failed: bool = False) -> InlineKeyboardMarkup:
    """Keyboard for post-image review. Optionally shows retry-failed button."""
    row = [InlineKeyboardButton(str(i + 1), callback_data=f"ca:edit:{i}") for i in range(n_slides)]
    buttons = [row[i:i + 5] for i in range(0, len(row), 5)]
    action_row = [InlineKeyboardButton("📄 Скачать PPTX", callback_data="ca:pptx:final")]
    if has_failed:
        action_row.append(InlineKeyboardButton("🔄 Повторить ❌", callback_data="ca:regen:failed:note"))
    action_row.append(InlineKeyboardButton("🔄 Пересоздать всё", callback_data="ca:regen:all"))
    buttons.append(action_row)
    buttons.append([
        InlineKeyboardButton("🖼 Все с замечанием", callback_data="ca:regen:all:imgnote"),
    ])
    buttons.append([
        InlineKeyboardButton("🍌 Промпты (с текстом)", callback_data="ca:prompt:text"),
        InlineKeyboardButton("🍌 Промпты (фон)",       callback_data="ca:prompt:notxt"),
    ])
    return InlineKeyboardMarkup(buttons)


def _slide_actions_keyboard(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Новый текст AI", callback_data=f"ca:edit:{idx}:ai"),
            InlineKeyboardButton("✏️ Свой текст",     callback_data=f"ca:edit:{idx}:manual"),
        ],
        [
            InlineKeyboardButton("🖼 Новая картинка",        callback_data=f"ca:edit:{idx}:img"),
            InlineKeyboardButton("🖼 С замечанием",          callback_data=f"ca:edit:{idx}:imgnote"),
        ],
        [
            InlineKeyboardButton("✅ Готово", callback_data="ca:review"),
        ],
    ])
