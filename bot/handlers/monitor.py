from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def notify_owner(text: str) -> None:
    """Send a notification to the owner via the monitor bot (sync, fire-and-forget)."""
    from config import settings

    token = settings.monitor_bot_token
    chat_id = settings.monitor_chat_id
    if not token or not chat_id:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("monitor notify failed: %s", exc)
