from __future__ import annotations

from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from config import settings
from bot.handlers.commands import start, trends, status, help_cmd, yt_thumbs_callback
from bot.handlers.errors import error_handler
from bot.handlers.keywords import build_keywords_handler
from bot.handlers.threads import build_threads_handler
from bot.handlers.carousel import build_carousel_handler


def build_application() -> Application:
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("trends", trends))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(build_keywords_handler())
    app.add_handler(CallbackQueryHandler(yt_thumbs_callback, pattern="^yt_thumbs$"))
    for h in build_threads_handler():
        app.add_handler(h)
    for h in build_carousel_handler():
        app.add_handler(h)

    app.add_error_handler(error_handler)

    return app
