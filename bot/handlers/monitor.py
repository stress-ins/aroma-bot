from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_recent_alerts: dict[str, float] = {}
_RECENT_ALERTS_MAX = 500


def _cleanup_recent_alerts() -> None:
    """Remove expired entries to prevent unbounded memory growth."""
    if len(_recent_alerts) <= _RECENT_ALERTS_MAX:
        return
    now = time.time()
    # Remove entries older than the longest reasonable cooldown (24h)
    expired = [k for k, ts in _recent_alerts.items() if now - ts > 86400]
    for k in expired:
        _recent_alerts.pop(k, None)
    # If still over limit, drop oldest entries
    if len(_recent_alerts) > _RECENT_ALERTS_MAX:
        sorted_keys = sorted(_recent_alerts, key=_recent_alerts.get)
        for k in sorted_keys[: len(_recent_alerts) - _RECENT_ALERTS_MAX]:
            _recent_alerts.pop(k, None)


def notify_owner_throttled(text: str, dedup_key: str, cooldown: int = 300) -> None:
    """Send a throttled notification — suppresses duplicates within cooldown seconds."""
    now = time.time()
    if now - _recent_alerts.get(dedup_key, 0) < cooldown:
        return
    _recent_alerts[dedup_key] = now
    _cleanup_recent_alerts()
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
