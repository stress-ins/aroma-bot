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


async def admin_costs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Usage: /costs [today|week|YYYY-MM-DD]"""
    if not update.message or not _is_admin(update):
        return

    from bot.services.cost_report import build_html_report, build_telegram_text
    from bot.services.cost_stats_store import (
        date_range_last7,
        date_range_today,
        get_cost_stats,
    )

    args = context.args or []
    arg = args[0].lower() if args else "today"

    if arg == "today":
        since, until = date_range_today()
        label = f"за {since}"
    elif arg == "week":
        since, until = date_range_last7()
        label = f"за 7 дней ({since} — {until})"
    else:
        since = until = arg
        label = f"за {since}"

    await update.message.reply_text("\u23f3 Считаю расходы...")

    try:
        stats = await get_cost_stats(since, until)
    except Exception as exc:
        await update.message.reply_text(f"\u274c Ошибка: {exc}")
        return

    text = build_telegram_text(stats, label)

    if len(text) <= 3800:
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        summary = "\n".join(text.split("\n")[:12]) + "\n\n\U0001f4ce <i>Полный отчёт в файле</i>"
        await update.message.reply_text(summary, parse_mode="HTML")
        import io

        html = build_html_report(stats, label)
        buf = io.BytesIO(html.encode("utf-8"))
        buf.name = f"costs_{since}.html"
        await update.message.reply_document(
            document=buf,
            filename=f"costs_{since}.html",
            caption=f"\U0001f4ca Полный отчёт {label}",
        )


async def admin_test_image_url_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test that a draft's images are publicly accessible."""
    if not update.message or not _is_admin(update):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /test_image_url <draft_id>")
        return

    draft_id = args[0].strip()
    from bot.services.drafts_store import get_draft
    from bot.services.publisher import _resolve_media_paths
    from bot.services.meta_publisher import _get_public_image_url, _get_carousel_image_urls
    import httpx

    draft = await get_draft(draft_id)
    if not draft:
        await update.message.reply_text(f"Draft {draft_id} not found.")
        return

    media_paths = _resolve_media_paths(draft.kind, draft.draft_id, draft.payload or {})

    if draft.kind == "carousel":
        urls = _get_carousel_image_urls(draft.payload or {}, draft_id, media_paths)
        if not urls:
            await update.message.reply_text("No carousel image URLs found in payload.")
            return
        test_url = urls[0]
        results = f"Found {len(urls)} slide URLs.\nTesting first:\n{test_url}\n\n"
    else:
        test_url = _get_public_image_url(draft.payload or {}, draft.kind, draft_id, media_paths)
        if not test_url:
            await update.message.reply_text("No public image URL found for this draft.")
            return
        results = f"URL: {test_url}\n\n"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.head(test_url)
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "?")
            size = resp.headers.get("content-length", "?")
            results += f"Accessible (HTTP {resp.status_code})\nType: {ct}\nSize: {size} bytes"
        else:
            results += f"HTTP {resp.status_code}"
    except Exception as exc:
        results += f"Request failed: {exc}"

    await update.message.reply_text(results)


def build_admin_handlers():
    return [
        CommandHandler("admin_users", admin_users_cmd),
        CommandHandler("admin_set", admin_set_cmd),
        CommandHandler("admin_promo_gen", admin_promo_gen_cmd),
        CommandHandler("admin_promo_list", admin_promo_list_cmd),
        CommandHandler("costs", admin_costs_cmd),
        CommandHandler("test_image_url", admin_test_image_url_cmd),
    ]
