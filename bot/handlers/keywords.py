from __future__ import annotations

import re
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from keywords.registry import TOPICS, apply_custom
from keywords.store import add_word, remove_word, FIELD_LABELS

logger = logging.getLogger(__name__)

# Conversation states
IDLE, ADD_TOPIC, ADD_FIELD, WAIT_WORD, RM_TOPIC = range(5)

FIELD_ORDER = ["kw_ru", "kw_en", "tag_ru", "tag_en"]
FIELD_ATTR = {
    "kw_ru": "keywords_ru",
    "kw_en": "keywords_en",
    "tag_ru": "hashtags_ru",
    "tag_en": "hashtags_en",
}

_ESCAPE_RE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def _esc(text: str) -> str:
    return _ESCAPE_RE.sub(r"\\\1", text)


def _format_keywords() -> str:
    lines = ["📚 *Ключевые слова по темам*\n"]
    for i, topic in enumerate(TOPICS, 1):
        lines.append(f"*{i}\\. {_esc(topic.name)}*")
        if topic.keywords_ru:
            lines.append(f"  🇷🇺 {_esc(', '.join(topic.keywords_ru))}")
        if topic.keywords_en:
            lines.append(f"  🇬🇧 {_esc(', '.join(topic.keywords_en))}")
        if topic.hashtags_ru:
            lines.append(f"  🏷🇷🇺 {_esc(', '.join(topic.hashtags_ru))}")
        if topic.hashtags_en:
            lines.append(f"  🏷🇬🇧 {_esc(', '.join(topic.hashtags_en))}")
        lines.append("")
    return "\n".join(lines)


def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("➕ Добавить", callback_data="kw:add"),
        InlineKeyboardButton("❌ Удалить", callback_data="kw:rm"),
    ]])


def _topics_kb(prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t.name, callback_data=f"{prefix}:{i}")]
        for i, t in enumerate(TOPICS)
    ]
    rows.append([InlineKeyboardButton("◀ Назад", callback_data="kw:back")])
    return InlineKeyboardMarkup(rows)


def _fields_kb(topic_idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(FIELD_LABELS["kw_ru"], callback_data=f"kw:a_f:{topic_idx}:kw_ru"),
            InlineKeyboardButton(FIELD_LABELS["kw_en"], callback_data=f"kw:a_f:{topic_idx}:kw_en"),
        ],
        [
            InlineKeyboardButton(FIELD_LABELS["tag_ru"], callback_data=f"kw:a_f:{topic_idx}:tag_ru"),
            InlineKeyboardButton(FIELD_LABELS["tag_en"], callback_data=f"kw:a_f:{topic_idx}:tag_en"),
        ],
        [InlineKeyboardButton("◀ Назад", callback_data="kw:add")],
    ])


def _words_kb(topic_idx: int) -> InlineKeyboardMarkup:
    topic = TOPICS[topic_idx]
    rows = []
    for fld in FIELD_ORDER:
        words = getattr(topic, FIELD_ATTR[fld])
        for widx, word in enumerate(words):
            rows.append([InlineKeyboardButton(
                f"❌ {word}",
                callback_data=f"kw:r_w:{topic_idx}:{fld}:{widx}",
            )])
    rows.append([InlineKeyboardButton("◀ Назад", callback_data="kw:rm")])
    return InlineKeyboardMarkup(rows)


# ── Entry point ────────────────────────────────────────────────────────────────

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _format_keywords(),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_main_kb(),
    )
    return IDLE


# ── Add flow ───────────────────────────────────────────────────────────────────

async def cb_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(_topics_kb("kw:a_t"))
    return ADD_TOPIC


async def cb_add_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    topic_idx = int(q.data.split(":")[-1])
    context.user_data["kw_topic"] = topic_idx
    await q.edit_message_reply_markup(_fields_kb(topic_idx))
    return ADD_FIELD


async def cb_add_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")          # kw:a_f:{idx}:{field}
    topic_idx = int(parts[2])
    fld = parts[3]
    context.user_data["kw_topic"] = topic_idx
    context.user_data["kw_field"] = fld
    topic = TOPICS[topic_idx]
    label = FIELD_LABELS[fld]
    await q.edit_message_text(
        f"✏️ Введи слово для *{_esc(topic.name)}* \\({_esc(label)}\\):\n\n_/cancel — отмена_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return WAIT_WORD


async def handle_word_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    word = update.message.text.strip()
    topic_idx: int = context.user_data.get("kw_topic")
    fld: str = context.user_data.get("kw_field")
    if topic_idx is None or fld is None:
        return ConversationHandler.END

    add_word(topic_idx, fld, word)
    apply_custom()

    topic = TOPICS[topic_idx]
    await update.message.reply_text(
        f"✅ Добавлено *{_esc(word)}* в *{_esc(topic.name)}*",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await update.message.reply_text(
        _format_keywords(),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_main_kb(),
    )
    return IDLE


# ── Remove flow ────────────────────────────────────────────────────────────────

async def cb_rm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(_topics_kb("kw:r_t"))
    return RM_TOPIC


async def cb_rm_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    topic_idx = int(q.data.split(":")[-1])
    await q.edit_message_reply_markup(_words_kb(topic_idx))
    return RM_TOPIC


async def cb_rm_word(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    parts = q.data.split(":")          # kw:r_w:{tidx}:{field}:{widx}
    topic_idx = int(parts[2])
    fld = parts[3]
    widx = int(parts[4])

    topic = TOPICS[topic_idx]
    words = getattr(topic, FIELD_ATTR[fld])
    if widx < len(words):
        word = words[widx]
        remove_word(topic_idx, fld, word)
        apply_custom()
        await q.answer(f"Удалено: {word}")
    else:
        await q.answer("Слово не найдено")

    await q.edit_message_text(
        _format_keywords(),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_main_kb(),
    )
    return IDLE


# ── Navigation ─────────────────────────────────────────────────────────────────

async def cb_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        _format_keywords(),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_main_kb(),
    )
    return IDLE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


# ── Handler builder ────────────────────────────────────────────────────────────

def build_keywords_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("keywords", keywords_cmd)],
        states={
            IDLE: [
                CallbackQueryHandler(cb_add, pattern=r"^kw:add$"),
                CallbackQueryHandler(cb_rm, pattern=r"^kw:rm$"),
            ],
            ADD_TOPIC: [
                CallbackQueryHandler(cb_add_topic, pattern=r"^kw:a_t:\d+$"),
                CallbackQueryHandler(cb_back, pattern=r"^kw:back$"),
            ],
            ADD_FIELD: [
                CallbackQueryHandler(cb_add_field, pattern=r"^kw:a_f:\d+:(kw_ru|kw_en|tag_ru|tag_en)$"),
                CallbackQueryHandler(cb_add, pattern=r"^kw:add$"),  # "Назад" from fields
            ],
            WAIT_WORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_word_input),
            ],
            RM_TOPIC: [
                CallbackQueryHandler(cb_rm_topic, pattern=r"^kw:r_t:\d+$"),
                CallbackQueryHandler(cb_rm_word, pattern=r"^kw:r_w:\d+:(kw_ru|kw_en|tag_ru|tag_en):\d+$"),
                CallbackQueryHandler(cb_rm, pattern=r"^kw:rm$"),    # "Назад" from word list
                CallbackQueryHandler(cb_back, pattern=r"^kw:back$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
