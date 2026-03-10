from __future__ import annotations

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler

from config import settings
from bot.handlers.commands import start, trends, status, help_cmd, yt_thumbs_callback
from bot.handlers.errors import error_handler
from bot.handlers.keywords import build_keywords_handler
from bot.handlers.threads import build_threads_handler
from bot.handlers.carousel import build_carousel_handler
from bot.handlers.content import build_content_handler
from bot.handlers.adapter import build_adapt_handler
from bot.handlers.planner import build_plan_handler
from bot.handlers.reels import build_reels_handler
from bot.handlers.threads_manager import build_threads_manager_handler


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
    from telegram.ext import filters as tg_filters
    for h in build_carousel_handler():
        # TEXT MessageHandler → group 2 (content=0, adapt=1, carousel=2)
        # PHOTO/Command/Callback handlers → group 0
        if isinstance(h, MessageHandler) and not (h.filters & tg_filters.PHOTO):
            app.add_handler(h, group=2)
        else:
            app.add_handler(h)
    for h in build_content_handler():
        app.add_handler(h)
    for h in build_adapt_handler():
        # MessageHandler goes to group 1 so content's group-0 MessageHandler doesn't swallow it
        if isinstance(h, MessageHandler):
            app.add_handler(h, group=1)
        else:
            app.add_handler(h)
    for h in build_plan_handler():
        app.add_handler(h)
    for h in build_reels_handler():
        app.add_handler(h)
    for h in build_threads_manager_handler():
        if isinstance(h, MessageHandler):
            app.add_handler(h, group=3)
        else:
            app.add_handler(h)

    app.add_error_handler(error_handler)

    return app
