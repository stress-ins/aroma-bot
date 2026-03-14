from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.agents import (
    ContentDraft,
    FORMAT_LABELS,
    GOAL_LABELS,
    format_content_message,
    format_label,
    generate_strategist_step,
    generate_topic_options,
    generate_writer_step,
    goal_label,
)
from config import settings
from bot.handlers.threads_manager import publish_threads_keyboard, threads_api_enabled
from bot.services.drafts_store import save_draft, update_draft
from bot.services.mini_app import append_mini_app_button

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    "trends": "Актуальные тренды",
    "prompt": "Свой запрос",
}

# Formats available in /content (carousel redirects to /carousel)
_CONTENT_FORMATS = {k: v for k, v in FORMAT_LABELS.items() if k != "carousel"}


def _goals_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(label, callback_data=f"ct:goal:{key}")
        for key, label in GOAL_LABELS.items()
    ]
    return InlineKeyboardMarkup([buttons[:2], buttons[2:]])


def _formats_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(label, callback_data=f"ct:format:{key}")
        for key, label in _CONTENT_FORMATS.items()
    ]
    buttons.append(InlineKeyboardButton("🎠 Карусель → /carousel", callback_data="ct:format:carousel"))
    return InlineKeyboardMarkup([buttons[:2], [buttons[2]], [buttons[3]]])


def _topics_keyboard(topics: list[str]) -> InlineKeyboardMarkup:
    topic_buttons = [
        InlineKeyboardButton(str(idx + 1), callback_data=f"ct:pick:{idx}")
        for idx in range(len(topics))
    ]
    rows = [topic_buttons[i:i + 5] for i in range(0, len(topic_buttons), 5)]
    rows.append([InlineKeyboardButton("🔄 Новые темы", callback_data="ct:topics:refresh")])
    return InlineKeyboardMarkup(rows)


def _draft_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Другой вариант", callback_data="ct:regen"),
            InlineKeyboardButton("✏️ Свой текст", callback_data="ct:edit:manual"),
        ],
        [
            InlineKeyboardButton("✅ Согласовать", callback_data="ct:approve"),
            InlineKeyboardButton("↩️ К темам", callback_data="ct:back:topics"),
        ],
    ])


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


async def cmd_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.anthropic_api_key:
        await update.message.reply_text("❌ Для /content нужен ANTHROPIC_API_KEY.")
        return

    for key in (
        "content_goal", "content_format", "content_source", "content_topics",
        "content_custom_brief", "content_awaiting_prompt",
        "content_last_topic", "content_last_goal", "content_last_format",
        "content_last_draft_id", "content_review_draft", "content_awaiting_manual_edit",
    ):
        context.user_data.pop(key, None)

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

    # ── Goal ──────────────────────────────────────────────────────────────────
    if data.startswith("ct:goal:"):
        goal_key = data.split(":")[2]
        context.user_data["content_goal"] = goal_key
        await query.message.edit_text(
            f"🎯 Цель: {goal_label(goal_key)}\n\nТеперь выбери формат:",
            reply_markup=_formats_keyboard(),
        )
        return

    # ── Format ────────────────────────────────────────────────────────────────
    if data.startswith("ct:format:"):
        format_key = data.split(":")[2]
        goal_key = context.user_data.get("content_goal")
        if not goal_key:
            await query.message.reply_text("❌ Сначала выбери цель через /content.")
            return

        if format_key == "carousel":
            await query.message.edit_text(
                f"🎯 Цель: {goal_label(goal_key)}\n\n"
                "🎠 Для карусели используй команду /carousel\n\n"
                "Там полный флоу: 6 слайдов с нарративной дугой, "
                "картинки с QA-агентом, PPTX с умным позиционированием текста."
            )
            return

        context.user_data["content_format"] = format_key
        await query.message.edit_text(
            f"🎯 Цель: {goal_label(goal_key)}\n🧩 Формат: {format_label(format_key)}\n\nВыбери, на чем строить темы:",
            reply_markup=_source_keyboard(),
        )
        return

    # ── Source ────────────────────────────────────────────────────────────────
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
                "Пришли одним сообщением своё направление.\n\n"
                "Например:\n"
                "- как через аромат мягко снимать офисный стресс\n"
                "- контент для корпоративных клиентов про wellbeing\n"
                "- идеи про вечерние ритуалы для нервной системы"
            )
            return

        await query.message.edit_text(
            f"🎯 Цель: {goal_label(goal_key)}\n🧩 Формат: {format_label(format_key)}\n"
            f"🧭 Источник: {_source_label(source_key)}\n\n⏳ Собираю тренды и ищу темы..."
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

    # ── Refresh topics ────────────────────────────────────────────────────────
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
                "Пришли заново своё направление одним сообщением."
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

    # ── Back to topics ────────────────────────────────────────────────────────
    if data == "ct:back:topics":
        topics = context.user_data.get("content_topics", [])
        goal_key = context.user_data.get("content_goal")
        format_key = context.user_data.get("content_format")
        source_key = context.user_data.get("content_source", "trends")
        if not topics or not goal_key or not format_key:
            await query.message.reply_text("❌ Темы устарели. Запусти /content заново.")
            return
        await query.message.reply_text(
            _topics_text(goal_key, format_key, topics, source_key),
            reply_markup=_topics_keyboard(topics),
        )
        return

    # ── Pick topic ────────────────────────────────────────────────────────────
    if data.startswith("ct:pick:"):
        topics: list[str] = context.user_data.get("content_topics", [])
        goal_key = context.user_data.get("content_goal")
        format_key = context.user_data.get("content_format")
        idx = int(data.split(":")[2])

        if not topics or idx >= len(topics) or not goal_key or not format_key:
            await query.message.reply_text("❌ Темы устарели. Запусти /content заново.")
            return

        topic = topics[idx]
        context.user_data["content_last_topic"] = topic
        context.user_data["content_last_goal"] = goal_key
        context.user_data["content_last_format"] = format_key

        await _generate_and_show_draft(query.message, context, topic, goal_key, format_key)
        return

    # ── Regenerate same topic ─────────────────────────────────────────────────
    if data == "ct:regen":
        topic = context.user_data.get("content_last_topic")
        goal_key = context.user_data.get("content_last_goal") or context.user_data.get("content_goal")
        format_key = context.user_data.get("content_last_format") or context.user_data.get("content_format")
        if not topic or not goal_key or not format_key:
            await query.message.reply_text("❌ Контекст потерян. Запусти /content заново.")
            return
        await _generate_and_show_draft(query.message, context, topic, goal_key, format_key)
        return

    if data == "ct:edit:manual":
        draft: dict = context.user_data.get("content_review_draft", {})
        if not draft:
            await query.message.reply_text("❌ Черновик не найден. Сгенерируй контент заново.")
            return
        context.user_data["content_awaiting_manual_edit"] = True
        await query.message.reply_text(
            "✏️ Пришли новый основной текст одним сообщением.\n"
            "Я заменю блок TEXT и оставлю review-кнопки."
        )
        return

    if data == "ct:approve":
        draft: dict = context.user_data.get("content_review_draft", {})
        draft_id = context.user_data.get("content_last_draft_id")
        if not draft or not draft_id:
            await query.message.reply_text("❌ Черновик не найден. Сгенерируй контент заново.")
            return
        updated = update_draft(draft_id, status="approved", payload=draft)
        resolved_draft_id = updated.draft_id if updated else draft_id
        await query.message.reply_text(
            f"✅ Черновик согласован.\n🗂 Draft ID: {resolved_draft_id}\n"
            f"Позже оцени результат через /drafts {resolved_draft_id}",
            reply_markup=append_mini_app_button(
                None,
                label="🧭 Открыть Draft в Mini App",
                draft_id=str(resolved_draft_id),
                tab="drafts",
            ),
        )
        return


async def _generate_and_show_draft(
    msg, context: ContextTypes.DEFAULT_TYPE, topic: str, goal_key: str, format_key: str
) -> None:
    """Run 3-agent chain with per-step status updates, then show draft."""
    status = await msg.reply_text(
        f"🎯 {goal_label(goal_key)} · {format_label(format_key)}\n"
        f"📌 {topic}\n\n"
        "🧠 Стратег: ищет угол и хук..."
    )

    # Step 1: Strategist
    try:
        angle, hook = await generate_strategist_step(topic, goal_key, format_key)
        angle_preview = (angle[:70] + "…") if len(angle) > 70 else angle
        try:
            await status.edit_text(
                f"🎯 {goal_label(goal_key)} · {format_label(format_key)}\n"
                f"📌 {topic}\n\n"
                f"🧠 Угол: {angle_preview}\n\n"
                "✍️ Автор: пишет текст..."
            )
        except Exception:
            pass
    except Exception:
        logger.exception("Strategist step failed")
        angle, hook = "", ""

    # Step 2: Writer + Editor
    try:
        draft = await generate_writer_step(topic, goal_key, format_key, angle, hook)
    except Exception:
        logger.exception("Writer step failed")
        await status.delete()
        await msg.reply_text("❌ Не удалось сгенерировать контент. Попробуй позже.")
        return

    try:
        await status.delete()
    except Exception:
        pass

    saved = save_draft(
        kind=format_key,
        topic=topic,
        source="/content",
        payload={
            "goal_key": goal_key,
            "format_key": format_key,
            "angle": draft.angle,
            "hook": draft.hook,
            "caption": draft.caption,
            "cta": draft.cta,
            "hashtags": draft.hashtags,
            "visual_prompt": draft.visual_prompt,
            "slides": draft.slides,
        },
    )
    context.user_data["content_last_draft_id"] = saved.draft_id
    context.user_data["content_review_draft"] = {
        "goal_key": goal_key,
        "format_key": format_key,
        "angle": draft.angle,
        "hook": draft.hook,
        "caption": draft.caption,
        "cta": draft.cta,
        "hashtags": draft.hashtags,
        "visual_prompt": draft.visual_prompt,
        "slides": draft.slides,
    }
    message = format_content_message(draft, topic, goal_key, format_key)
    await msg.reply_text(
        f"{message}\n\n🗂 Draft ID: {saved.draft_id}",
        reply_markup=append_mini_app_button(
            _draft_keyboard(),
            label="🧭 Открыть Draft в Mini App",
            draft_id=saved.draft_id,
            tab="drafts",
        ),
    )

    # Publish button — via publisher (upload-post) if draft exists
    if format_key == "threads" and draft.caption and threads_api_enabled():
        context.user_data["threads_publish_text"] = draft.caption
        context.user_data["threads_publish_draft_id"] = saved.draft_id
        await msg.reply_text(
            "Если текст готов, можешь опубликовать прямо отсюда или через Mini App:",
            reply_markup=publish_threads_keyboard(),
        )


async def msg_content_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("content_awaiting_manual_edit"):
        draft_payload: dict = context.user_data.get("content_review_draft", {})
        draft_id = context.user_data.get("content_last_draft_id")
        topic = context.user_data.get("content_last_topic")
        goal_key = context.user_data.get("content_last_goal")
        format_key = context.user_data.get("content_last_format")
        text = (update.message.text or "").strip()

        if not draft_payload or not draft_id or not topic or not goal_key or not format_key:
            context.user_data["content_awaiting_manual_edit"] = False
            await update.message.reply_text("❌ Контекст редактирования потерян. Сгенерируй контент заново.")
            return
        if len(text) < 5:
            await update.message.reply_text("❌ Текст слишком короткий. Пришли полную версию.")
            return

        draft_payload["caption"] = text
        context.user_data["content_review_draft"] = draft_payload
        context.user_data["content_awaiting_manual_edit"] = False
        update_draft(draft_id, status="draft", payload=draft_payload)

        draft = ContentDraft(
            angle=str(draft_payload.get("angle", "")),
            hook=str(draft_payload.get("hook", "")),
            caption=str(draft_payload.get("caption", "")),
            cta=str(draft_payload.get("cta", "")),
            hashtags=str(draft_payload.get("hashtags", "")),
            visual_prompt=str(draft_payload.get("visual_prompt", "")),
            slides=list(draft_payload.get("slides", [])),
        )
        message = format_content_message(draft, topic, goal_key, format_key)
        await update.message.reply_text(
            f"{message}\n\n🗂 Draft ID: {draft_id}",
            reply_markup=append_mini_app_button(
                _draft_keyboard(),
                label="🧭 Открыть Draft в Mini App",
                draft_id=str(draft_id),
                tab="drafts",
            ),
        )
        return

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
