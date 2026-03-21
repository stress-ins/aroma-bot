from __future__ import annotations

import logging

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler

from config import settings

logger = logging.getLogger(__name__)
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
from bot.handlers.link_detector import build_link_detector_handlers


USER_COMMANDS = [
    BotCommand("trends", "Аналитика трендов (RU + EN)"),
    BotCommand("content", "Создать контент: цель → формат → тема → материал"),
    BotCommand("threads", "Пост для Threads + картинка"),
    BotCommand("carousel", "Карусель из 5 слайдов"),
    BotCommand("reels", "Сценарий для Reels"),
    BotCommand("adapt", "Адаптация поста под платформу"),
    BotCommand("plan", "Контент-план на неделю"),
    BotCommand("drafts", "Последние черновики"),
    BotCommand("keywords", "Ключевые слова"),
    BotCommand("app", "Открыть Mini App"),
    BotCommand("status", "Активные источники данных"),
    BotCommand("help", "Список команд"),
]

ADMIN_EXTRA_COMMANDS = [
    BotCommand("admin_users", "Управление пользователями"),
    BotCommand("admin_set", "Настройки бота"),
    BotCommand("costs", "Статистика расходов API"),
]


async def _post_init(application: Application) -> None:
    bot = application.bot

    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeAllPrivateChats())

    admin_id = settings.admin_telegram_id
    await bot.set_my_commands(
        USER_COMMANDS + ADMIN_EXTRA_COMMANDS,
        scope=BotCommandScopeChat(chat_id=admin_id),
    )

    await bot.set_my_short_description(
        "Тренды ароматерапии, контент для соцсетей, AI-помощник",
    )
    await bot.set_my_description(
        "Слежу за трендами ароматерапии, генерирую контент для соцсетей, "
        "помогаю с Threads, Reels, каруселями и контент-планами.",
    )
    logger.info("Bot commands and descriptions registered")


def build_application() -> Application:
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(60)
        .post_init(_post_init)
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

    for h in build_link_detector_handlers():
        if isinstance(h, MessageHandler):
            app.add_handler(h, group=4)
        else:
            app.add_handler(h)

    app.add_error_handler(error_handler)

    return app
