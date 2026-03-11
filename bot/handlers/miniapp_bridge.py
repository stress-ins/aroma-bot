from __future__ import annotations

import json

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from bot.handlers.drafts import open_draft_by_id


def parse_webapp_payload(raw: str) -> dict[str, str] | None:
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    normalized = {str(key): str(value) for key, value in data.items()}
    if not normalized.get("action"):
        return None
    return normalized


async def handle_miniapp_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.web_app_data:
        return

    payload = parse_webapp_payload(message.web_app_data.data)
    if not payload:
        await message.reply_text("❌ Не удалось прочитать данные из Mini App.")
        return

    action = payload.get("action", "")
    if action == "open_draft":
        draft_id = payload.get("draft_id", "").strip()
        if not draft_id:
            await message.reply_text("❌ Draft ID не передан из Mini App.")
            return
        await open_draft_by_id(update, context, draft_id)
        return

    await message.reply_text("❌ Неизвестное действие из Mini App.")


def build_miniapp_bridge_handler():
    return [
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_miniapp_webapp_data),
    ]
