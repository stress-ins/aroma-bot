"""Bot handler for /promo command — promo code activation."""
from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.services.subscription_store import activate_promo, get_or_create_user, effective_tier

TIER_LABELS = {
    "free": "Базовый (Free)",
    "student": "Студент",
    "expert": "Эксперт",
}


async def promo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Использование: /promo <код>\n\nПример: /promo AROMA-X7K2"
        )
        return

    code = args[0].strip().upper()
    telegram_id = update.effective_user.id

    promo = await activate_promo(telegram_id, code)
    if promo is None:
        await update.message.reply_text(
            "Промокод не найден, уже использован или истёк срок действия.\n"
            "Проверьте код и попробуйте снова."
        )
        return

    tier_label = TIER_LABELS.get(promo.tier, promo.tier)
    await update.message.reply_text(
        f"Тариф активирован: {tier_label} на {promo.duration_days} дней.\n"
        f"Откройте мини-аппу для доступа ко всем функциям."
    )


def build_subscription_handlers():
    return [CommandHandler("promo", promo_cmd)]
