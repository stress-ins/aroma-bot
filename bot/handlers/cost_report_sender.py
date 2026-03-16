"""Send cost reports to monitor chat — text or HTML file."""
from __future__ import annotations

import io
import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

_MAX_TEXT_LEN = 3800  # Telegram message limit is 4096; keep margin


def _send_message(text: str) -> None:
    token = settings.monitor_bot_token
    chat_id = settings.monitor_chat_id
    if not token or not chat_id:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("send_message failed: %s", exc)


def _send_html_file(html: str, filename: str, caption: str) -> None:
    token = settings.monitor_bot_token
    chat_id = settings.monitor_chat_id
    if not token or not chat_id:
        return
    try:
        buf = io.BytesIO(html.encode("utf-8"))
        buf.name = filename
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendDocument",
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"document": (filename, buf, "text/html")},
            timeout=15,
        )
    except Exception as exc:
        logger.warning("send_html_file failed: %s", exc)


async def send_cost_report(stats: dict[str, Any], period_label: str = "") -> None:
    from bot.services.cost_report import build_html_report, build_telegram_text

    text = build_telegram_text(stats, period_label)

    if len(text) <= _MAX_TEXT_LEN:
        _send_message(text)
    else:
        # Send short summary + HTML file
        summary_lines = text.split("\n")[:10]
        summary = "\n".join(summary_lines) + "\n\n\U0001f4ce <i>Полный отчёт в файле</i>"
        _send_message(summary)
        html = build_html_report(stats, period_label)
        filename = f"cost_report_{stats['since']}.html"
        _send_html_file(html, filename, f"\U0001f4ca Отчёт {period_label or stats['since']}")
