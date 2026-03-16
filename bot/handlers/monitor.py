from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_recent_alerts: dict[str, float] = {}


def notify_owner_throttled(text: str, dedup_key: str, cooldown: int = 300) -> None:
    """Send a throttled notification — suppresses duplicates within cooldown seconds."""
    now = time.time()
    if now - _recent_alerts.get(dedup_key, 0) < cooldown:
        return
    _recent_alerts[dedup_key] = now
    notify_owner(text)


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
