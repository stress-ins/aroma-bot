from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.agents.adapter import ADAPT_PLATFORM_LABELS, adapt_text_sync
from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _platforms_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(label, callback_data=f"ad:platform:{key}")
        for key, label in ADAPT_PLATFORM_LABELS.items()
    ]
    return InlineKeyboardMarkup([buttons[:2], buttons[2:]])


async def cmd_adapt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.anthropic_api_key:
        await update.message.reply_text("❌ Для /adapt нужен ANTHROPIC_API_KEY.")
        return

    context.user_data.pop("adapt_awaiting_text", None)
    context.user_data.pop("adapt_original_text", None)

    context.user_data["adapt_awaiting_text"] = True
    await update.message.reply_text(
        "✍️ *Адаптация поста под платформу*\n\n"
        "Отправь текст поста, который хочешь адаптировать.",
        parse_mode="Markdown",
    )


async def msg_adapt_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("adapt_awaiting_text"):
        return

    text = (update.message.text or "").strip()
    if len(text) < 10:
        await update.message.reply_text("❌ Текст слишком короткий. Пришли полный пост.")
        return

    context.user_data["adapt_awaiting_text"] = False
    context.user_data["adapt_original_text"] = text

    await update.message.reply_text(
        "✅ Текст получен. Выбери целевую платформу:",
        reply_markup=_platforms_keyboard(),
    )


async def cb_adapt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("ad:platform:"):
        platform_key = data.split(":")[2]
        original_text = context.user_data.get("adapt_original_text", "")
        if not original_text:
            await query.message.reply_text("❌ Текст не найден. Запусти /adapt заново.")
            return

        platform_label = ADAPT_PLATFORM_LABELS.get(platform_key, platform_key)
        status = await query.message.reply_text(
            f"⏳ Адаптирую под {platform_label}..."
        )

        loop = asyncio.get_event_loop()
        adapted = await loop.run_in_executor(_executor, adapt_text_sync, original_text, platform_key)

        other_buttons = [
            InlineKeyboardButton(label, callback_data=f"ad:platform:{key}")
            for key, label in ADAPT_PLATFORM_LABELS.items()
            if key != platform_key
        ]
        keyboard = [
            [InlineKeyboardButton("🔄 Адаптировать ещё раз", callback_data=f"ad:platform:{platform_key}")],
        ]
        if other_buttons:
            keyboard.append(other_buttons[:2])
            if len(other_buttons) > 2:
                keyboard.append(other_buttons[2:])
        await status.edit_text(
            f"📱 *{platform_label}:*\n\n{adapted}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


def build_adapt_handler():
    return [
        CommandHandler("adapt", cmd_adapt),
        CallbackQueryHandler(cb_adapt, pattern="^ad:"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, msg_adapt_text),
    ]
