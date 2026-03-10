from __future__ import annotations

import logging
import traceback

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception:", exc_info=context.error)
    tb = "".join(traceback.format_exception(type(context.error), context.error, context.error.__traceback__))
    logger.debug("Traceback:\n%s", tb)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Произошла ошибка. Попробуй ещё раз позже."
            )
        except Exception:
            pass

    # Notify owner via monitor bot
    try:
        from bot.handlers.monitor import notify_owner

        err_type = type(context.error).__name__
        short_tb = tb[-1500:] if len(tb) > 1500 else tb
        user_info = ""
        if isinstance(update, Update) and update.effective_user:
            user_info = f"\n👤 User: {update.effective_user.id}"
        cmd_info = ""
        if isinstance(update, Update) and update.effective_message and update.effective_message.text:
            cmd_info = f"\n💬 Msg: {update.effective_message.text[:100]}"

        msg = (
            f"⚠️ <b>aroma-bot error: {err_type}</b>"
            f"{user_info}{cmd_info}\n\n"
            f"<pre>{short_tb}</pre>"
        )
        notify_owner(msg)
    except Exception:
        pass
