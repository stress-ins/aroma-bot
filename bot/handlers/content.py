from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.agents import (
    FORMAT_LABELS,
    GOAL_LABELS,
    format_content_message,
    format_label,
    generate_content_draft,
    generate_image_bytes,
    generate_topic_options,
    goal_label,
    make_single_image_prompt,
    make_slide_prompts_no_text,
    make_slide_prompts_with_text,
)
from config import settings
from bot.handlers.threads_manager import publish_threads_keyboard, threads_api_enabled

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    "trends": "Актуальные тренды",
    "prompt": "Свой запрос",
}

DEFAULT_CAROUSEL_IMAGE_PROMPT = (
    "warm sensory wellness scene, terracotta beige sage palette, natural textures, "
    "soft light, calm atmospheric composition --ar 4:5 --style atmospheric"
)


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


def _source_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📈 На основе трендов", callback_data="ct:source:trends"),
        InlineKeyboardButton("✍️ Свой запрос", callback_data="ct:source:prompt"),
    ]])


def _source_label(source_key: str) -> str:
    return SOURCE_LABELS.get(source_key, source_key)


def _topics_text(goal_key: str, format_key: str, topics: list[str], source_key: str) -> str:
    items = "\n".join(f"{idx + 1}. {topic}" for idx, topic in enumerate(topics))
    return (
        f"🎯 Цель: {goal_label(goal_key)}\n"
        f"🧩 Формат: {format_label(format_key)}\n\n"
        f"🧭 Источник: {_source_label(source_key)}\n\n"
        f"Выбери тему:\n\n{items}\n\n"
        "Нажми на цифру ниже."
    )


def _prompt_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🖼 С текстом", callback_data="ct:prompt:text"),
        InlineKeyboardButton("🖼 Без текста", callback_data="ct:prompt:notxt"),
    ]])


async def cmd_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.anthropic_api_key:
        await update.message.reply_text("❌ Для /content нужен ANTHROPIC_API_KEY.")
        return

    context.user_data.pop("content_goal", None)
    context.user_data.pop("content_format", None)
    context.user_data.pop("content_source", None)
    context.user_data.pop("content_topics", None)
    context.user_data.pop("content_custom_brief", None)
    context.user_data.pop("content_awaiting_prompt", None)
    context.user_data.pop("content_slides", None)
    context.user_data.pop("content_img_prompt", None)

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
            f"🎯 Цель: {goal_label(goal_key)}\n🧩 Формат: {format_label(format_key)}\n\nВыбери, на чем строить темы:",
            reply_markup=_source_keyboard(),
        )
        return

    if data.startswith("ct:source:"):
        source_key = data.split(":")[2]
        goal_key = context.user_data.get("content_goal")
        format_key = context.user_data.get("content_format")
        if not goal_key or not format_key:
            await query.message.reply_text("❌ Контекст потерян. Запусти /content заново.")
            return

        context.user_data["content_source"] = source_key
        context.user_data["content_topics"] = []
        context.user_data["content_awaiting_prompt"] = False

        if source_key == "prompt":
            context.user_data["content_awaiting_prompt"] = True
            await query.message.edit_text(
                f"🎯 Цель: {goal_label(goal_key)}\n"
                f"🧩 Формат: {format_label(format_key)}\n"
                f"🧭 Источник: {_source_label(source_key)}\n\n"
                "Пришли одним сообщением свое направление.\n\n"
                "Например:\n"
                "- как через аромат мягко снимать офисный стресс\n"
                "- контент для корпоративных клиентов про wellbeing\n"
                "- идеи про вечерние ритуалы для нервной системы"
            )
            return

        await query.message.edit_text(
            f"🎯 Цель: {goal_label(goal_key)}\n🧩 Формат: {format_label(format_key)}\n🧭 Источник: {_source_label(source_key)}\n\n⏳ Собираю тренды и ищу темы..."
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
            _topics_text(goal_key, format_key, topics, source_key),
            reply_markup=_topics_keyboard(topics),
        )
        return

    if data == "ct:topics:refresh":
        goal_key = context.user_data.get("content_goal")
        format_key = context.user_data.get("content_format")
        source_key = context.user_data.get("content_source")
        custom_brief = context.user_data.get("content_custom_brief", "")
        if not goal_key or not format_key or not source_key:
            await query.message.reply_text("❌ Контекст потерян. Запусти /content заново.")
            return

        await query.message.edit_text(
            f"🎯 Цель: {goal_label(goal_key)}\n"
            f"🧩 Формат: {format_label(format_key)}\n"
            f"🧭 Источник: {_source_label(source_key)}\n\n"
            "⏳ Обновляю темы..."
        )

        results = None
        if source_key == "trends":
            results = cache.get("results")
            if not results:
                results = await collect_all()
                cache.set("results", results)
        elif not custom_brief:
            context.user_data["content_awaiting_prompt"] = True
            await query.message.edit_text(
                f"🎯 Цель: {goal_label(goal_key)}\n"
                f"🧩 Формат: {format_label(format_key)}\n"
                f"🧭 Источник: {_source_label(source_key)}\n\n"
                "Пришли заново свое направление одним сообщением."
            )
            return

        topics = await generate_topic_options(results, goal_key, format_key, user_brief=custom_brief)
        if not topics:
            await query.message.edit_text("❌ Не удалось обновить темы. Попробуй позже.")
            return

        context.user_data["content_topics"] = topics
        await query.message.edit_text(
            _topics_text(goal_key, format_key, topics, source_key),
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
        status = await query.message.reply_text(
            f"✍️ Генерирую контент.\n\nЦель: {goal_label(goal_key)}\nФормат: {format_label(format_key)}\nТема: {topic}"
        )
        draft = await generate_content_draft(topic, goal_key, format_key)
        message = format_content_message(draft, topic, goal_key, format_key)
        await status.delete()
        await query.message.reply_text(message)

        if format_key == "threads" and draft.caption and threads_api_enabled():
            context.user_data["threads_publish_text"] = draft.caption
            await query.message.reply_text(
                "Если текст готов, можешь отправить его прямо в Threads:",
                reply_markup=publish_threads_keyboard(),
            )

        if format_key == "carousel" and draft.slides:
            context.user_data["content_slides"] = draft.slides
            base_prompt = draft.visual_prompt or DEFAULT_CAROUSEL_IMAGE_PROMPT
            context.user_data["content_img_prompt"] = base_prompt

            if not settings.image_api_key:
                await query.message.reply_text(
                    "⚠️ Автогенерация картинок недоступна.\nВыбери, какие промпты показать:",
                    reply_markup=_prompt_buttons(),
                )
                return

            media: list[InputMediaPhoto] = []
            loop = asyncio.get_event_loop()
            for slide_idx, slide in enumerate(draft.slides, 1):
                image_prompt = make_single_image_prompt(base_prompt, slide, with_text=True)
                image_bytes = await loop.run_in_executor(None, generate_image_bytes, image_prompt)
                if image_bytes:
                    media.append(InputMediaPhoto(media=image_bytes, caption=f"Слайд {slide_idx}: {slide}"))

            if media and len(media) == len(draft.slides):
                for start in range(0, len(media), 10):
                    await query.message.reply_media_group(media[start:start + 10])
                await query.message.reply_text(
                    "Если захочешь вручную доработать визуалы в Canva, вот кнопки с prompt'ами:",
                    reply_markup=_prompt_buttons(),
                )
            else:
                await query.message.reply_text(
                    "⚠️ Картинки не удалось сгенерировать автоматически.\nВыбери, какие промпты показать:",
                    reply_markup=_prompt_buttons(),
                )
        return

    if data == "ct:prompt:text":
        slides = context.user_data.get("content_slides", [])
        img_prompt = context.user_data.get("content_img_prompt", "")
        if not slides or not img_prompt:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        await query.message.reply_text(make_slide_prompts_with_text(img_prompt, slides))
        return

    if data == "ct:prompt:notxt":
        slides = context.user_data.get("content_slides", [])
        img_prompt = context.user_data.get("content_img_prompt", "")
        if not slides or not img_prompt:
            await query.message.reply_text("❌ Данные устарели. Сгенерируй карусель заново.")
            return
        await query.message.reply_text(make_slide_prompts_no_text(img_prompt, slides))
        return


async def msg_content_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("content_awaiting_prompt"):
        return

    goal_key = context.user_data.get("content_goal")
    format_key = context.user_data.get("content_format")
    source_key = context.user_data.get("content_source")
    user_brief = (update.message.text or "").strip()

    if not goal_key or not format_key or source_key != "prompt":
        context.user_data["content_awaiting_prompt"] = False
        await update.message.reply_text("❌ Контекст потерян. Запусти /content заново.")
        return

    if len(user_brief) < 5:
        await update.message.reply_text("❌ Направление слишком короткое. Пришли чуть подробнее.")
        return

    context.user_data["content_awaiting_prompt"] = False
    context.user_data["content_custom_brief"] = user_brief

    status = await update.message.reply_text(
        f"🎯 Цель: {goal_label(goal_key)}\n"
        f"🧩 Формат: {format_label(format_key)}\n"
        f"🧭 Источник: {_source_label(source_key)}\n\n"
        "⏳ Генерирую темы по твоему запросу..."
    )

    topics = await generate_topic_options(None, goal_key, format_key, user_brief=user_brief)
    if not topics:
        await status.edit_text("❌ Не удалось сгенерировать темы. Попробуй переформулировать запрос.")
        return

    context.user_data["content_topics"] = topics
    await status.edit_text(
        _topics_text(goal_key, format_key, topics, source_key),
        reply_markup=_topics_keyboard(topics),
    )


def build_content_handler():
    return [
        CommandHandler("content", cmd_content),
        CallbackQueryHandler(cb_content, pattern="^ct:"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, msg_content_prompt),
    ]
