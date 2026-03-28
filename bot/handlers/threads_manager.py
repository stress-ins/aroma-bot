from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.agents.threads_replies import suggest_replies_sync
from bot.services.threads_api import ThreadsAPIError, ThreadsCandidate, ThreadsClient, collect_inbox_candidates_sync
from config import settings

_executor = ThreadPoolExecutor(max_workers=3)


def threads_api_enabled() -> bool:
    return settings.is_threads_api_enabled


def publish_threads_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📤 Опубликовать", callback_data="tm:publish:last"),
    ]])


def _suggestions_keyboard(count: int) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(str(i + 1), callback_data=f"tm:suggest:{i}") for i in range(count)]
    rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
    rows.append([InlineKeyboardButton("🔄 Обновить inbox", callback_data="tm:refresh")])
    return InlineKeyboardMarkup(rows)


def _reply_actions_keyboard(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Опубликовать ответ", callback_data=f"tm:approve:{idx}")],
        [InlineKeyboardButton("✍️ Изменить ответ", callback_data=f"tm:edit:{idx}")],
        [InlineKeyboardButton("↩️ К списку", callback_data="tm:refresh")],
    ])


def _render_suggestion(candidate: ThreadsCandidate, reason: str, reply_text: str, idx: int, total: int) -> str:
    lines = [
        f"🧵 Кандидат {idx + 1}/{total}",
        f"Автор: @{candidate.author}",
        f"Источник: {candidate.source}",
        f"Ссылка: {candidate.permalink or 'нет'}",
        "",
        "Почему стоит ответить:",
        reason,
        "",
        "Исходное сообщение:",
        candidate.text,
    ]
    if candidate.root_text:
        lines.extend(["", "Корневой пост:", candidate.root_text])
    lines.extend(["", "Черновик ответа:", reply_text])
    return "\n".join(lines)


async def cmd_threads_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not threads_api_enabled():
        await update.message.reply_text(
            "❌ Threads API не настроен.\nНужны THREADS_ACCESS_TOKEN и THREADS_USER_ID."
        )
        return

    status = await update.message.reply_text("🔍 Проверяю подключенный Threads-аккаунт...")
    loop = asyncio.get_event_loop()

    def _load_profile():
        client = ThreadsClient()
        me = client.get_me()
        target = client.lookup_profile(settings.threads_username) if settings.threads_username else None
        return me, target

    try:
        me, target = await loop.run_in_executor(_executor, _load_profile)
    except ThreadsAPIError as exc:
        await status.edit_text(f"❌ Не удалось проверить Threads API.\n{exc}")
        return

    lines = [
        "✅ Threads API подключен",
        f"Текущий аккаунт: @{me.get('username', 'unknown')}",
        f"User ID: {me.get('id', 'unknown')}",
    ]
    if settings.threads_username:
        lines.append(f"Ожидаемый аккаунт: @{settings.threads_username}")
        if target:
            lines.append(f"Profile lookup: @{target.get('username', 'unknown')} ({target.get('id', 'unknown')})")
        if str(me.get("username", "")).lower() == settings.threads_username.lower():
            lines.append("Совпадение: да")
        else:
            lines.append("Совпадение: нет")
    await status.edit_text("\n".join(lines))


async def cmd_threads_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    status = await update.message.reply_text("📥 Анализирую Threads inbox...")
    await _refresh_inbox_status(status, context)


async def _refresh_inbox_status(status_message, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not threads_api_enabled():
        await status_message.edit_text(
            "❌ Threads API не настроен.\nНужны THREADS_ACCESS_TOKEN и THREADS_USER_ID."
        )
        return
    if not settings.anthropic_api_key:
        await status_message.edit_text("❌ Для /threads_inbox нужен ANTHROPIC_API_KEY.")
        return

    loop = asyncio.get_event_loop()

    try:
        me, candidates = await loop.run_in_executor(_executor, collect_inbox_candidates_sync)
    except ThreadsAPIError as exc:
        await status_message.edit_text(f"❌ Не удалось загрузить Threads inbox.\n{exc}")
        return

    if not candidates:
        await status_message.edit_text("✅ Сейчас нет явных кандидатов для ответа в Threads.")
        return

    suggestions = await loop.run_in_executor(_executor, suggest_replies_sync, candidates)
    if not suggestions:
        await status_message.edit_text("⚠️ Кандидаты найдены, но Claude не предложил уверенные ответы.")
        return

    context.user_data["tm_me_username"] = str(me.get("username", ""))
    context.user_data["tm_candidates"] = candidates
    context.user_data["tm_suggestions"] = suggestions

    preview = []
    for idx, suggestion in enumerate(suggestions, 1):
        candidate = candidates[suggestion.candidate_index]
        preview.append(f"{idx}. @{candidate.author}: {candidate.text[:90]}")

    await status_message.edit_text(
        "📥 Нашел, на что стоит ответить в Threads:\n\n" + "\n".join(preview),
        reply_markup=_suggestions_keyboard(len(suggestions)),
    )


async def cb_threads_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "tm:publish:last":
        text = context.user_data.get("threads_publish_text", "").strip()
        if not text:
            await query.message.reply_text("❌ Текст для публикации не найден. Сгенерируй пост заново.")
            return
        draft_id = context.user_data.get("threads_publish_draft_id", "")
        if draft_id:
            from bot.services.publisher import publish
            status = await query.message.reply_text("📤 Публикую через ...")
            try:
                results = await publish(draft_id, ["threads"])
                threads_result = results.get("threads", {})
                if threads_result.get("status") == "success":
                    await status.edit_text(f"✅ Опубликовано.\nRequest ID: {threads_result.get('external_id', 'n/a')}")
                else:
                    await status.edit_text(f"❌ Ошибка: {threads_result.get('error', 'unknown')}")
            except Exception as exc:
                await status.edit_text(f"❌ Не удалось опубликовать.\n{exc}")
        else:
            # Fallback: direct Threads API for legacy posts without draft
            status = await query.message.reply_text("🚀 Публикую пост в Threads...")
            loop = asyncio.get_event_loop()
            try:
                post_id = await loop.run_in_executor(_executor, lambda: ThreadsClient().publish_text_post(text))
            except ThreadsAPIError as exc:
                await status.edit_text(f"❌ Не удалось опубликовать пост.\n{exc}")
                return
            await status.edit_text(f"✅ Пост опубликован в Threads.\nPost ID: {post_id}")
        return

    if data == "tm:refresh":
        await query.message.reply_text("📥 Обновляю Threads inbox...")
        temp = await query.message.reply_text("⏳ Смотрю новые кандидаты...")
        await _refresh_inbox_status(temp, context)
        return

    if data.startswith("tm:suggest:"):
        suggestions = context.user_data.get("tm_suggestions", [])
        candidates = context.user_data.get("tm_candidates", [])
        idx = int(data.split(":")[2])
        if idx >= len(suggestions):
            await query.message.reply_text("❌ Кандидаты устарели. Запусти /threads_inbox заново.")
            return
        suggestion = suggestions[idx]
        candidate = candidates[suggestion.candidate_index]
        await query.message.reply_text(
            _render_suggestion(candidate, suggestion.reason, suggestion.draft_reply, idx, len(suggestions)),
            reply_markup=_reply_actions_keyboard(idx),
        )
        return

    if data.startswith("tm:edit:"):
        idx = int(data.split(":")[2])
        suggestions = context.user_data.get("tm_suggestions", [])
        if idx >= len(suggestions):
            await query.message.reply_text("❌ Кандидаты устарели. Запусти /threads_inbox заново.")
            return
        context.user_data["tm_edit_index"] = idx
        await query.message.reply_text("✍️ Пришли новую версию ответа одним сообщением.")
        return

    if data.startswith("tm:approve:"):
        idx = int(data.split(":")[2])
        suggestions = context.user_data.get("tm_suggestions", [])
        candidates = context.user_data.get("tm_candidates", [])
        if idx >= len(suggestions):
            await query.message.reply_text("❌ Кандидаты устарели. Запусти /threads_inbox заново.")
            return
        suggestion = suggestions[idx]
        candidate = candidates[suggestion.candidate_index]
        status = await query.message.reply_text("🚀 Публикую ответ в Threads...")
        loop = asyncio.get_event_loop()
        try:
            reply_id = await loop.run_in_executor(
                _executor,
                lambda: ThreadsClient().publish_text_post(suggestion.draft_reply, reply_to_id=candidate.thread_id),
            )
        except ThreadsAPIError as exc:
            await status.edit_text(f"❌ Не удалось опубликовать ответ.\n{exc}")
            return
        await status.edit_text(
            f"✅ Ответ опубликован.\nReply ID: {reply_id}\nСсылка: {candidate.permalink or 'нет'}"
        )
        return


async def msg_threads_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    edit_index = context.user_data.get("tm_edit_index")
    if edit_index is None:
        return

    suggestions = context.user_data.get("tm_suggestions", [])
    candidates = context.user_data.get("tm_candidates", [])
    text = (update.message.text or "").strip()

    if not text:
        await update.message.reply_text("❌ Ответ пустой. Пришли новый текст целиком.")
        return
    if edit_index >= len(suggestions):
        context.user_data.pop("tm_edit_index", None)
        await update.message.reply_text("❌ Кандидаты устарели. Запусти /threads_inbox заново.")
        return

    suggestions[edit_index].draft_reply = text
    context.user_data["tm_suggestions"] = suggestions
    context.user_data.pop("tm_edit_index", None)

    suggestion = suggestions[edit_index]
    candidate = candidates[suggestion.candidate_index]
    await update.message.reply_text(
        _render_suggestion(candidate, suggestion.reason, suggestion.draft_reply, edit_index, len(suggestions)),
        reply_markup=_reply_actions_keyboard(edit_index),
    )


def build_threads_manager_handler():
    return [
        CommandHandler("threads_account", cmd_threads_account),
        CommandHandler("threads_inbox", cmd_threads_inbox),
        CommandHandler("threads_trends", cmd_threads_trends),
        CallbackQueryHandler(cb_threads_manager, pattern="^tm:"),
        CallbackQueryHandler(cb_trend_threads, pattern="^tt:"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, msg_threads_manager),
    ]



# ── Thread Trends Monitor ──────────────────────────────────────────────────


async def cmd_threads_trends(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not threads_api_enabled():
        await update.message.reply_text("❌ Threads API не настроен.")
        return

    from bot.services.tracked_threads_store import list_tracked_threads

    threads = await list_tracked_threads(status="new", min_score=0.5, limit=10)
    if not threads:
        await update.message.reply_text(
            "🧵 Нет новых релевантных веток в Threads.\n"
            "Мониторинг запускается каждые 2 часа автоматически.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Запустить мониторинг", callback_data="tt:scan")],
            ]),
        )
        return

    lines = [f"🧵 Релевантные ветки в Threads ({len(threads)}):\n"]
    for i, t in enumerate(threads, 1):
        action_emoji = {"reply": "💬", "create_content": "✍️", "engage": "👍"}.get(t.suggested_action, "👀")
        lines.append(
            f"{i}. @{t.author_username} — {t.ai_summary or t.text[:80]}\n"
            f"   {action_emoji} {t.suggested_action or '?'} | {t.relevance_score:.0%}\n"
        )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"{i}. @{t.author_username[:20]}", callback_data=f"tt:view:{t.thread_id}")]
            for i, t in enumerate(threads[:5], 1)
        ]
        + [[InlineKeyboardButton("🔄 Запустить мониторинг", callback_data="tt:scan")]]
    )
    await update.message.reply_text("\n".join(lines), reply_markup=keyboard)


async def cb_trend_threads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "tt:scan":
        await query.message.reply_text("⏳ Запускаю мониторинг Threads...")
        try:
            from bot.services.thread_monitor import run_thread_monitor
            count = await run_thread_monitor()
            await query.message.reply_text(
                f"✅ Мониторинг завершён. Найдено {count} релевантных веток.\n"
                f"Запустите /threads_trends для просмотра."
            )
        except Exception as exc:
            await query.message.reply_text(f"❌ Ошибка мониторинга: {exc}")
        return

    parts = data.split(":", 2)
    if len(parts) < 3:
        return
    action, thread_id = parts[1], parts[2]

    from bot.services.tracked_threads_store import get_tracked_thread, update_tracked_status

    thread = await get_tracked_thread(thread_id)
    if not thread:
        await query.message.reply_text("❌ Ветка не найдена.")
        return

    if action == "view":
        text = (
            f"🧵 @{thread.author_username}\n"
            f"Релевантность: {thread.relevance_score:.0%} | {thread.suggested_action or '?'}\n\n"
            f"{thread.text[:600]}\n"
        )
        if thread.root_text:
            text += f"\nКорневой пост:\n{thread.root_text[:300]}\n"
        if thread.content_angle:
            text += f"\n💡 Угол для контента: {thread.content_angle}\n"
        if thread.permalink:
            text += f"\n🔗 {thread.permalink}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Ответить в ветке", callback_data=f"tt:reply:{thread_id}")],
            [InlineKeyboardButton("✍️ Создать пост на эту тему", callback_data=f"tt:content:{thread_id}")],
            [InlineKeyboardButton("🚫 Не релевантно", callback_data=f"tt:dismiss:{thread_id}")],
        ])
        await query.message.reply_text(text, reply_markup=keyboard)

    elif action == "reply":
        await query.message.reply_text("✍️ Генерирую ответ...")
        loop = asyncio.get_event_loop()
        candidate = ThreadsCandidate(
            thread_id=thread.thread_id,
            source="keyword_match",
            author=thread.author_username,
            text=thread.text,
            permalink=thread.permalink,
            timestamp=thread.found_at.isoformat() if thread.found_at else "",
            root_text=thread.root_text,
        )
        try:
            suggestions = await loop.run_in_executor(_executor, suggest_replies_sync, [candidate])
        except Exception as exc:
            await query.message.reply_text(f"❌ Не удалось сгенерировать ответ: {exc}")
            return
        if not suggestions:
            await query.message.reply_text("❌ Claude не предложил ответ для этой ветки.")
            return
        context.user_data["tm_candidates"] = [candidate]
        context.user_data["tm_suggestions"] = suggestions
        suggestion = suggestions[0]
        await query.message.reply_text(
            _render_suggestion(candidate, suggestion.reason, suggestion.draft_reply, 0, 1),
            reply_markup=_reply_actions_keyboard(0),
        )

    elif action == "content":
        if not thread.content_angle:
            await query.message.reply_text("❌ Нет угла для контента по этой ветке.")
            return
        await query.message.reply_text(f"✍️ Создаю черновик поста на тему:\n«{thread.content_angle}»")
        try:
            from bot.agents.content import generate_content_draft
            from bot.services.drafts_store import save_draft
            draft = await generate_content_draft(topic=thread.content_angle, goal_key="trust", format_key="threads")
            saved = await save_draft(
                kind="threads", topic=thread.content_angle, source="thread_monitor",
                payload={"angle": draft.angle, "hook": draft.hook, "caption": draft.caption,
                         "cta": draft.cta, "hashtags": draft.hashtags,
                         "source_thread": thread.permalink, "source_keyword": thread.keyword_matched},
            )
            await update_tracked_status(thread.thread_id, "content_created")
            await query.message.reply_text(
                f"✅ Черновик создан: #{saved.seq_id or '?'}\n"
                f"Тема: {thread.content_angle}\n"
                f"Откройте Mini App → Контент для редактирования."
            )
        except Exception as exc:
            await query.message.reply_text(f"❌ Не удалось создать черновик: {exc}")

    elif action == "dismiss":
        await update_tracked_status(thread_id, "dismissed")
        await query.message.reply_text("🚫 Ветка помечена как нерелевантная.")
