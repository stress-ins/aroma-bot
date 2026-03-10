from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.agents.planner import generate_plan_sync
from bot.handlers.threads import _format_trends
from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.anthropic_api_key:
        await update.message.reply_text("❌ Для /plan нужен ANTHROPIC_API_KEY.")
        return

    from cache.store import cache
    from analytics.aggregator import collect_all

    results = cache.get("results")
    if not results:
        msg = await update.message.reply_text("⏳ Собираю тренды для плана...")
        results = await collect_all()
        cache.set("results", results)
        await msg.delete()

    status = await update.message.reply_text("📅 Составляю контент-план на неделю...")

    trends_text = _format_trends(results)

    loop = asyncio.get_event_loop()
    plan = await loop.run_in_executor(_executor, generate_plan_sync, trends_text)

    if not plan:
        await status.edit_text("❌ Не удалось составить план. Попробуй позже.")
        return

    await status.edit_text(f"📅 *Контент-план на неделю:*\n\n{plan}", parse_mode="Markdown")


def build_plan_handler():
    return [
        CommandHandler("plan", cmd_plan),
    ]
