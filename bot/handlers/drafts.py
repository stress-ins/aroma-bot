from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.services.drafts_store import list_recent_drafts


def _drafts_text(limit: int = 10) -> str:
    drafts = list_recent_drafts(limit=limit)
    if not drafts:
        return (
            "🗂 Черновиков пока нет.\n\n"
            "Сгенерируй что-нибудь через /content или /reels — я сохраню это в историю."
        )

    lines = ["🗂 Последние черновики:\n"]
    for idx, draft in enumerate(drafts, 1):
        lines.append(
            f"{idx}. [{draft.kind}] {draft.topic}\n"
            f"ID: {draft.draft_id} · Источник: {draft.source}"
        )
    lines.append("\nСледующий шаг: добавим открытие и переиспользование черновика по ID.")
    return "\n\n".join(lines)


async def cmd_drafts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_drafts_text())


def build_drafts_handler():
    return [
        CommandHandler("drafts", cmd_drafts),
    ]
