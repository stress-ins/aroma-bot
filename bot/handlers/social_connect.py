from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes

from bot.services.social_oauth import (
    build_instagram_authorize_url,
    build_oauth_state,
    build_threads_authorize_url,
)
from config import settings


THREADS_REDIRECT_URI = "https://oauth.aromara.ru/threads/callback"
INSTAGRAM_REDIRECT_URI = "https://oauth.aromara.ru/instagram/callback"


async def cmd_threads_connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.threads_app_id or not settings.threads_app_secret:
        await update.message.reply_text(
            "❌ Threads OAuth не настроен.\nНужны THREADS_APP_ID и THREADS_APP_SECRET в .env."
        )
        return
    if not update.effective_chat or not update.effective_user:
        return

    state = build_oauth_state(
        secret=settings.telegram_bot_token,
        service="threads",
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
    )
    url = build_threads_authorize_url(
        client_id=settings.threads_app_id,
        redirect_uri=THREADS_REDIRECT_URI,
        state=state,
    )
    await update.message.reply_text(
        "🔗 Подключаем Threads.\n\n"
        "Нажмите кнопку ниже, пройдите авторизацию, и бот сам сохранит токен на VPS.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Подключить Threads", url=url)]]
        ),
    )


async def cmd_instagram_connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.instagram_app_id or not settings.instagram_app_secret:
        await update.message.reply_text(
            "❌ Instagram OAuth не настроен.\nНужны INSTAGRAM_APP_ID и INSTAGRAM_APP_SECRET в .env."
        )
        return
    if not update.effective_chat or not update.effective_user:
        return

    state = build_oauth_state(
        secret=settings.telegram_bot_token,
        service="instagram",
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
    )
    url = build_instagram_authorize_url(
        client_id=settings.instagram_app_id,
        redirect_uri=INSTAGRAM_REDIRECT_URI,
        state=state,
    )
    await update.message.reply_text(
        "🔗 Подключаем Instagram.\n\n"
        "Нажмите кнопку ниже, пройдите авторизацию, и бот сам сохранит токен на VPS.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Подключить Instagram", url=url)]]
        ),
    )


def build_social_connect_handlers():
    return [
        CommandHandler("threads_connect", cmd_threads_connect),
        CommandHandler("instagram_connect", cmd_instagram_connect),
    ]
