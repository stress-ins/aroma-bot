from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from bot.agents import (
    FORMAT_LABELS,
    GOAL_LABELS,
    format_content_message,
    format_label,
    generate_content_draft,
    generate_topic_options,
    goal_label,
)
from config import settings

logger = logging.getLogger(__name__)


def _goals_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(label, callback_data=f"ct:goal:{key}")
        for key, label in GOAL_LABELS.items()
    ]
    return InlineKeyboardMarkup([buttons[:2], buttons[2:]])


def _formats_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(label, callback_data=f"ct:format:{key}")
        for key, label in FORMAT_LABELS.items()
    ]
    return InlineKeyboardMarkup([buttons[:2], buttons[2:]])


def _topics_keyboard(topics: list[str]) -> InlineKeyboardMarkup:
    topic_buttons = [
        InlineKeyboardButton(str(idx + 1), callback_data=f"ct:pick:{idx}")
        for idx in range(len(topics))
    ]
    rows = [topic_buttons[i:i + 5] for i in range(0, len(topic_buttons), 5)]
    rows.append([InlineKeyboardButton("🔄 Новые темы", callback_data="ct:topics:refresh")])
    return InlineKeyboardMarkup(rows)


def _topics_text(goal_key: str, format_key: str, topics: list[str]) -> str:
    items = "\n".join(f"{idx + 1}. {topic}" for idx, topic in enumerate(topics))
    return (
        f"🎯 Цель: {goal_label(goal_key)}\n"
        f"🧩 Формат: {format_label(format_key)}\n\n"
        f"Выбери тему:\n\n{items}\n\n"
        "Нажми на цифру ниже."
    )


async def cmd_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.anthropic_api_key:
        await update.message.reply_text("❌ Для /content нужен ANTHROPIC_API_KEY.")
        return

    context.user_data.pop("content_goal", None)
    context.user_data.pop("content_format", None)
    context.user_data.pop("content_topics", None)

    await update.message.reply_text(
        "🧠 Контент-агенты готовы.\n\nВыбери цель контента:",
        reply_markup=_goals_keyboard(),
    )


async def cb_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from analytics.aggregator import collect_all
    from cache.store import cache

    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("ct:goal:"):
        goal_key = data.split(":")[2]
        context.user_data["content_goal"] = goal_key
        await query.message.edit_text(
            f"🎯 Цель: {goal_label(goal_key)}\n\nТеперь выбери формат:",
            reply_markup=_formats_keyboard(),
        )
        return

    if data.startswith("ct:format:"):
        format_key = data.split(":")[2]
        goal_key = context.user_data.get("content_goal")
        if not goal_key:
            await query.message.reply_text("❌ Сначала выбери цель через /content.")
            return

        context.user_data["content_format"] = format_key
        await query.message.edit_text(
            f"🎯 Цель: {goal_label(goal_key)}\n🧩 Формат: {format_label(format_key)}\n\n⏳ Собираю тренды и ищу темы..."
        )

        results = cache.get("results")
        if not results:
            results = await collect_all()
            cache.set("results", results)

        topics = await generate_topic_options(results, goal_key, format_key)
        if not topics:
            await query.message.edit_text("❌ Не удалось сгенерировать темы. Попробуй позже.")
            return

        context.user_data["content_topics"] = topics
        await query.message.edit_text(
            _topics_text(goal_key, format_key, topics),
            reply_markup=_topics_keyboard(topics),
        )
        return

    if data == "ct:topics:refresh":
        goal_key = context.user_data.get("content_goal")
        format_key = context.user_data.get("content_format")
        if not goal_key or not format_key:
            await query.message.reply_text("❌ Контекст потерян. Запусти /content заново.")
            return

        await query.message.edit_text(
            f"🎯 Цель: {goal_label(goal_key)}\n🧩 Формат: {format_label(format_key)}\n\n⏳ Обновляю темы..."
        )
        results = cache.get("results")
        if not results:
            results = await collect_all()
            cache.set("results", results)

        topics = await generate_topic_options(results, goal_key, format_key)
        if not topics:
            await query.message.edit_text("❌ Не удалось обновить темы. Попробуй позже.")
            return

        context.user_data["content_topics"] = topics
        await query.message.edit_text(
            _topics_text(goal_key, format_key, topics),
            reply_markup=_topics_keyboard(topics),
        )
        return

    if data.startswith("ct:pick:"):
        topics: list[str] = context.user_data.get("content_topics", [])
        goal_key = context.user_data.get("content_goal")
        format_key = context.user_data.get("content_format")
        idx = int(data.split(":")[2])

        if not topics or idx >= len(topics) or not goal_key or not format_key:
            await query.message.reply_text("❌ Темы устарели. Запусти /content заново.")
            return

        topic = topics[idx]
        await query.message.reply_text(
            f"✍️ Генерирую контент.\n\nЦель: {goal_label(goal_key)}\nФормат: {format_label(format_key)}\nТема: {topic}"
        )
        draft = await generate_content_draft(topic, goal_key, format_key)
        message = format_content_message(draft, topic, goal_key, format_key)

        await query.message.reply_text(message)
        return


def build_content_handler():
    return [
        CommandHandler("content", cmd_content),
        CallbackQueryHandler(cb_content, pattern="^ct:"),
    ]
