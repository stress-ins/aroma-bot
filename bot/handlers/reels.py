from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from bot.agents.reels_agent import generate_reels_scenario_sync, generate_reels_topics_sync
from bot.handlers.threads import _format_trends
from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _topics_keyboard(topics: list[str]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(str(i + 1), callback_data=f"rl:pick:{i}") for i in range(len(topics))]
    buttons = [row[i:i + 5] for i in range(0, len(row), 5)]
    buttons.append([InlineKeyboardButton("🔄 Обновить темы", callback_data="rl:refresh")])
    return InlineKeyboardMarkup(buttons)


def _topics_text(topics: list[str]) -> str:
    items = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    return f"🎬 *Темы для Reels:*\n\n{items}\n\nНажми номер — получишь детальный сценарий:"


async def _load_topics(context: ContextTypes.DEFAULT_TYPE, results: list) -> list[str]:
    trends_text = _format_trends(results)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, generate_reels_topics_sync, trends_text)


async def cmd_reels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.anthropic_api_key:
        await update.message.reply_text("❌ Для /reels нужен ANTHROPIC_API_KEY.")
        return

    from cache.store import cache
    from analytics.aggregator import collect_all

    results = cache.get("results")
    if not results:
        msg = await update.message.reply_text("⏳ Собираю тренды...")
        results = await collect_all()
        cache.set("results", results)
        await msg.delete()

    status = await update.message.reply_text("🎬 Генерирую темы для Reels...")
    topics = await _load_topics(context, results)

    if not topics:
        await status.edit_text("❌ Не удалось сгенерировать темы. Попробуй позже.")
        return

    context.user_data["rl_topics"] = topics
    await status.edit_text(
        _topics_text(topics),
        parse_mode="Markdown",
        reply_markup=_topics_keyboard(topics),
    )


async def cb_reels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cache.store import cache

    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "rl:refresh":
        results = cache.get("results")
        if not results:
            await query.message.edit_text("⏳ Нет данных. Запусти /reels заново.")
            return
        await query.message.edit_text("🎬 Обновляю темы...")
        topics = await _load_topics(context, results)
        if not topics:
            await query.message.edit_text("❌ Не удалось обновить темы.")
            return
        context.user_data["rl_topics"] = topics
        await query.message.edit_text(
            _topics_text(topics),
            parse_mode="Markdown",
            reply_markup=_topics_keyboard(topics),
        )
        return

    if data.startswith("rl:pick:"):
        idx = int(data.split(":")[2])
        topics: list[str] = context.user_data.get("rl_topics", [])
        if not topics or idx >= len(topics):
            await query.message.reply_text("❌ Темы устарели — запусти /reels заново.")
            return

        topic = topics[idx]
        status = await query.message.reply_text(
            f"🎬 Тема: {topic}\n\n⏳ Пишу сценарий..."
        )

        loop = asyncio.get_event_loop()
        scenario = await loop.run_in_executor(_executor, generate_reels_scenario_sync, topic)

        await status.edit_text(
            f"🎬 *Сценарий Reels:* {topic}\n\n{scenario}",
            parse_mode="Markdown",
        )


def build_reels_handler():
    return [
        CommandHandler("reels", cmd_reels),
        CallbackQueryHandler(cb_reels, pattern="^rl:"),
    ]
