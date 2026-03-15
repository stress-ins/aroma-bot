"""Admin bot commands — user management, promo code generation."""
from __future__ import annotations

from datetime import timezone

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.services.subscription_store import (
    create_promo_codes,
    list_promo_codes,
    list_users,
    set_subscription,
)
from config import settings


def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == settings.admin_telegram_id)


async def admin_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not _is_admin(update):
        return

    args = context.args or []
    page = int(args[0]) if args and args[0].isdigit() else 1
    limit = 20
    offset = (page - 1) * limit

    users = await list_users(limit=limit, offset=offset)
    if not users:
        await update.message.reply_text("Пользователи не найдены.")
        return

    lines = ["<b>Пользователи:</b>"]
    for u in users:
        trial = u.trial_ends_at.strftime("%Y-%m-%d") if u.trial_ends_at else "—"
        created = u.created_at.strftime("%Y-%m-%d")
        lines.append(f"• <code>{u.telegram_id}</code> | {u.tier} | trial: {trial} | reg: {created}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def admin_set_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not _is_admin(update):
        return

    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Использование: /admin_set <telegram_id> <tier> [days]")
        return

    try:
        telegram_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Неверный telegram_id.")
        return

    tier = args[1].lower()
    if tier not in ("free", "student", "expert"):
        await update.message.reply_text("Тариф должен быть: free / student / expert")
        return

    days: int | None = None
    if len(args) >= 3:
        try:
            days = int(args[2])
        except ValueError:
            await update.message.reply_text("days должен быть числом.")
            return

    await set_subscription(telegram_id, tier, days)
    days_str = f" на {days} дней" if days else " (бессрочно)"
    await update.message.reply_text(
        f"Подписка <code>{telegram_id}</code> → <b>{tier}</b>{days_str} установлена.",
        parse_mode="HTML",
    )


async def admin_promo_gen_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not _is_admin(update):
        return

    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Использование: /admin_promo_gen <tier> <days> [count=1] [prefix=AROMA]"
        )
        return

    tier = args[0].lower()
    if tier not in ("student", "expert"):
        await update.message.reply_text("Тариф должен быть: student / expert")
        return

    try:
        days = int(args[1])
    except ValueError:
        await update.message.reply_text("days должен быть числом.")
        return

    count = int(args[2]) if len(args) >= 3 and args[2].isdigit() else 1
    prefix = args[3].upper() if len(args) >= 4 else "AROMA"

    if count > 50:
        await update.message.reply_text("Максимум 50 кодов за раз.")
        return

    codes = await create_promo_codes(tier=tier, duration_days=days, count=count, prefix=prefix)
    code_list = "\n".join(f"• <code>{c}</code>" for c in codes)
    await update.message.reply_text(
        f"Созданы промокоды ({tier}, {days} дн.):\n{code_list}",
        parse_mode="HTML",
    )


async def admin_promo_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not _is_admin(update):
        return

    promos = await list_promo_codes()
    if not promos:
        await update.message.reply_text("Промокоды не найдены.")
        return

    lines = ["<b>Промокоды:</b>"]
    for p in promos[:30]:
        exp = p.expires_at.strftime("%Y-%m-%d") if p.expires_at else "∞"
        lines.append(
            f"• <code>{p.code}</code> | {p.tier} | {p.duration_days}д | {p.uses_count}/{p.max_uses} | до {exp}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


def build_admin_handlers():
    return [
        CommandHandler("admin_users", admin_users_cmd),
        CommandHandler("admin_set", admin_set_cmd),
        CommandHandler("admin_promo_gen", admin_promo_gen_cmd),
        CommandHandler("admin_promo_list", admin_promo_list_cmd),
    ]
