"""Publisher for Telegram channel via Bot API."""

from __future__ import annotations

import logging
from typing import Any

from bot.services.drafts_store import get_draft
from bot.services.approval_workflow import mark_published, mark_failed
from bot.services.publish_log_store import save_log, update_log_status

logger = logging.getLogger(__name__)


def _draft_text(payload: dict[str, Any], kind: str) -> str:
    if kind == "carousel":
        slides = payload.get("slides") or []
        return "\n\n".join(str(s) for s in slides if s)
    return str(payload.get("text", "") or payload.get("post", ""))


async def publish_item(
    draft_id: str,
    bot: Any,
    chat_id: str,
) -> dict[str, Any]:
    """Send draft text to a Telegram channel/chat.

    Calls mark_published or mark_failed from approval_workflow on completion.
    """
    if not bot or not chat_id:
        return {"status": "failed", "error": "Telegram bot or chat_id not provided"}

    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")

    log_id = await save_log(draft_id, "telegram", "publish", "pending")
    text = _draft_text(draft.payload, draft.kind)

    try:
        msg = await bot.send_message(chat_id=chat_id, text=text)
        external_id = str(msg.message_id)
        await update_log_status(log_id, "success", external_id=external_id)
        try:
            await mark_published(draft_id, {"telegram": external_id})
        except Exception:
            logger.exception("Failed to update workflow status for draft %s", draft_id)
        return {"status": "success", "external_id": external_id}
    except Exception as exc:
        error_msg = str(exc)[:500]
        await update_log_status(log_id, "failed", error_message=error_msg)
        try:
            await mark_failed(draft_id, error_msg)
        except Exception:
            logger.exception("Failed to update workflow status for draft %s", draft_id)
        return {"status": "failed", "error": error_msg}
