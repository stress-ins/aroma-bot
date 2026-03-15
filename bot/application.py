from __future__ import annotations

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler

from config import settings
from bot.handlers.commands import start, trends, status, help_cmd, open_mini_app, yt_thumbs_callback
from bot.handlers.errors import error_handler
from bot.handlers.keywords import build_keywords_handler
from bot.handlers.threads import build_threads_handler
from bot.handlers.carousel import build_carousel_handler
from bot.handlers.content import build_content_handler
from bot.handlers.adapter import build_adapt_handler
from bot.handlers.planner import build_plan_handler
from bot.handlers.reels import build_reels_handler
from bot.handlers.drafts import build_drafts_handler
from bot.handlers.miniapp_bridge import build_miniapp_bridge_handler
from bot.handlers.threads_manager import build_threads_manager_handler
from bot.handlers.social_connect import build_social_connect_handlers
from bot.handlers.subscription import build_subscription_handlers
from bot.handlers.admin import build_admin_handlers


def build_application() -> Application:
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(60)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("trends", trends))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("app", open_mini_app))
    for h in build_social_connect_handlers():
        app.add_handler(h)
    for h in build_miniapp_bridge_handler():
        app.add_handler(h)
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
    for h in build_drafts_handler():
        app.add_handler(h)
    for h in build_threads_manager_handler():
        if isinstance(h, MessageHandler):
            app.add_handler(h, group=3)
        else:
            app.add_handler(h)

    for h in build_subscription_handlers():
        app.add_handler(h)
    for h in build_admin_handlers():
        app.add_handler(h)

    app.add_error_handler(error_handler)

    return app
