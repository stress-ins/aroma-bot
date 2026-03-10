"""Standalone monitoring bot for the VPS.

Commands (owner only):
  /status   — systemctl status for all services
  /load     — CPU / RAM / disk
  /logs     — last 30 lines of aroma-bot journal
  /restart  — restart aroma-bot
"""
from __future__ import annotations

import asyncio
import logging
import subprocess

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

MONITOR_BOT_TOKEN = "211516795:AAHqQ5UwsgM9SYngGBNAWF5UPUhsN9SHoFs"
OWNER_CHAT_ID = 62912125

SERVICES = [
    ("aroma-bot",       "🤖 Aroma Bot"),
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
        "/logs — последние 30 строк логов aroma-bot\n"
        "/restart — перезапустить aroma-bot\n"
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
async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Перезапускаю aroma-bot...")
    result = _run("systemctl restart aroma-bot && echo OK || echo FAIL")
    status = _run("systemctl is-active aroma-bot")
    icon = "✅" if status == "active" else "❌"
    await update.message.reply_text(
        f"{icon} aroma-bot: <code>{status}</code>\nresult: {result}",
        parse_mode="HTML",
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
    app.add_handler(CommandHandler("restart", cmd_restart))

    logger.info("Monitor bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
