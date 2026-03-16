"""Standalone monitoring bot for the VPS.

Commands (owner only):
  /status   — systemctl status for all services
  /load     — CPU / RAM / disk
  /logs     — last 30 lines of aroma-bot journal
  /errors   — last 5 WARNING/ERROR lines from aroma-bot journal
  /restart  — restart aroma-bot
  /costs    — API cost stats (today/week/date)
"""
from __future__ import annotations

import asyncio
import logging
import subprocess

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import settings

MONITOR_BOT_TOKEN = settings.monitor_bot_token
OWNER_CHAT_ID = settings.admin_telegram_id

SERVICES = [
    ("aroma-bot",       "🤖 Aroma Bot"),
    ("aroma-miniapp",   "🧭 Mini App"),
    ("aromara-site",    "🌐 Сайт aromara.ru"),
    ("threads-oauth",   "🔑 Threads OAuth"),
    ("nginx",           "⚙️ Nginx"),
]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _run(cmd: str, timeout: int = 10) -> str:
    try:
        out = subprocess.check_output(
            cmd, shell=True, stderr=subprocess.STDOUT, timeout=timeout
        )
        return out.decode(errors="replace").strip()
    except subprocess.CalledProcessError as e:
        return e.output.decode(errors="replace").strip()
    except Exception as exc:
        return f"error: {exc}"


def _owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or update.effective_user.id != OWNER_CHAT_ID:
            return
        await func(update, context)
    return wrapper


@_owner_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🛠 <b>Monitor Bot</b>\n\n"
        "/status — статус всех сервисов\n"
        "/load — нагрузка на сервер (CPU/RAM/диск)\n"
        "/logs [N] — последние N строк логов aroma-bot (по умолч. 30)\n"
        "/errors — последние 5 WARNING/ERROR из aroma-bot\n"
        "/restart — перезапустить aroma-bot\n"
        "/costs [today|week|YYYY-MM-DD] — расходы API\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


@_owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["<b>📊 Статус сервисов:</b>\n"]
    for svc, label in SERVICES:
        active = _run(f"systemctl is-active {svc}")
        enabled = _run(f"systemctl is-enabled {svc} 2>/dev/null")
        since = _run(
            f"systemctl show {svc} --property=ActiveEnterTimestamp "
            f"| cut -d= -f2 | cut -d' ' -f2-3"
        )
        icon = "✅" if active == "active" else "❌"
        lines.append(f"{icon} <b>{label}</b>")
        lines.append(f"   состояние: <code>{active}</code> ({enabled})")
        if since:
            lines.append(f"   с: {since}")
        lines.append("")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@_owner_only
async def cmd_load(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uptime = _run("uptime -p")
    load = _run("cat /proc/loadavg | awk '{print $1\"/\"$2\"/\"$3}'")
    cpu_count = _run("nproc")
    mem = _run("free -h | awk '/^Mem/ {print $3\"/\"$2\" (use: \"$3/$2*100\"%\"}'")
    mem_lines = _run(
        "free -h | awk '/^Mem/ {printf \"%s / %s (%.0f%%)\", $3, $2, $3/$2*100}'"
    )
    disk = _run("df -h / | awk 'NR==2 {print $3\"/\"$2\" (\"$5\")\"}'")
    swap = _run("free -h | awk '/^Swap/ {print $3\"/\"$2}'")

    text = (
        f"<b>🖥 Нагрузка на сервер</b>\n\n"
        f"⏱ Uptime: {uptime}\n"
        f"📈 Load avg (1/5/15m): <code>{load}</code> (CPU: {cpu_count})\n"
        f"💾 RAM: <code>{mem_lines}</code>\n"
        f"💿 Диск /: <code>{disk}</code>\n"
        f"🔄 Swap: <code>{swap}</code>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


@_owner_only
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    n = 30
    args = context.args
    if args and args[0].isdigit():
        n = min(int(args[0]), 100)

    raw = _run(f"journalctl -u aroma-bot -n {n} --no-pager --output=short")
    # Telegram limit 4096, trim from start if needed
    if len(raw) > 3800:
        raw = "...(обрезано)...\n" + raw[-3800:]
    await update.message.reply_text(f"<pre>{raw}</pre>", parse_mode="HTML")


@_owner_only
async def cmd_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Pull last 500 lines, filter WARNING/ERROR, take last 5 matches
    raw = _run(
        "journalctl -u aroma-bot -n 500 --no-pager --output=short "
        "| grep -E ' (WARNING|ERROR|CRITICAL|warn|error) ' | tail -5"
    )
    if not raw:
        await update.message.reply_text("✅ Ошибок и предупреждений не найдено.")
        return
    if len(raw) > 3800:
        raw = "...(обрезано)...\n" + raw[-3800:]
    await update.message.reply_text(f"<b>⚠️ Последние ошибки aroma-bot:</b>\n\n<pre>{raw}</pre>", parse_mode="HTML")


@_owner_only
async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Перезапускаю aroma-bot...")
    result = _run("systemctl restart aroma-bot && echo OK || echo FAIL")
    status = _run("systemctl is-active aroma-bot")
    icon = "✅" if status == "active" else "❌"
    await update.message.reply_text(
        f"{icon} aroma-bot: <code>{status}</code>\nresult: {result}",
        parse_mode="HTML",
    )


@_owner_only
async def cmd_costs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    await update.message.reply_text("⏳ Считаю расходы...")

    try:
        stats = await get_cost_stats(since, until)
    except Exception as exc:
        await update.message.reply_text(f"❌ Ошибка: {exc}")
        return

    text = build_telegram_text(stats, label)

    if len(text) <= 3800:
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        import io

        summary = "\n".join(text.split("\n")[:12]) + "\n\n📎 <i>Полный отчёт в файле</i>"
        await update.message.reply_text(summary, parse_mode="HTML")
        html = build_html_report(stats, label)
        buf = io.BytesIO(html.encode("utf-8"))
        buf.name = f"costs_{since}.html"
        await update.message.reply_document(
            document=buf,
            filename=f"costs_{since}.html",
            caption=f"📊 Полный отчёт {label}",
        )


def main() -> None:
    app = (
        Application.builder()
        .token(MONITOR_BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("load", cmd_load))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("errors", cmd_errors))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("costs", cmd_costs))

    logger.info("Monitor bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
