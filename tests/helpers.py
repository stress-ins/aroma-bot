"""Shared test helpers — data factories, Telegram mock factories, utility functions.

Centralises duplicated helpers from test_miniapp, test_utils, test_subscription, etc.
Import from here instead of re-defining in each test file.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from db.models import AromaCardModel, UserProfile


# ---------------------------------------------------------------------------
# Data factories
# ---------------------------------------------------------------------------

def make_user(telegram_id: int = 12345, tier: str = "free", **kw) -> MagicMock:
    """Create a MagicMock with spec=UserProfile and sensible defaults."""
    user = MagicMock(spec=UserProfile)
    user.telegram_id = telegram_id
    user.tier = tier
    user.trial_ends_at = kw.pop("trial_ends_at", None)
    user.daily_oil_subscribed = kw.pop("daily_oil_subscribed", True)
    user.created_at = kw.pop("created_at", None)
    user.updated_at = kw.pop("updated_at", None)
    for k, v in kw.items():
        setattr(user, k, v)
    return user


def make_aroma_card(slug: str = "lavender", name: str = "Лаванда", **kw) -> AromaCardModel:
    """Create a real AromaCardModel instance (can be added to DB session)."""
    return AromaCardModel(
        slug=slug,
        name=name,
        category=kw.pop("category", "aroma"),
        source_type=kw.pop("source_type", "herb"),
        aliases=kw.pop("aliases", []),
        payload=kw.pop("payload", {}),
        **kw,
    )


def make_draft_kwargs(
    draft_id: str = "test001",
    kind: str = "threads",
    topic: str = "Test topic",
    source: str = "/content",
    status: str = "draft",
    **kw,
) -> dict:
    """Return kwargs suitable for DraftRecord(...) or DraftModel(...)."""
    from datetime import datetime, timezone

    return {
        "draft_id": draft_id,
        "kind": kind,
        "topic": topic,
        "source": source,
        "status": status,
        "feedback": kw.pop("feedback", ""),
        "payload": kw.pop("payload", {}),
        "created_at": kw.pop("created_at", datetime.now(timezone.utc).isoformat()),
        **kw,
    }


# ---------------------------------------------------------------------------
# File reading helpers
# ---------------------------------------------------------------------------

_MINIAPP_STATIC = Path("miniapp", "static")


def miniapp_static_text(*relative_parts: str) -> str:
    """Read a file from miniapp/static/ and return its text content."""
    return (_MINIAPP_STATIC / Path(*relative_parts)).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Telegram mock factories
# ---------------------------------------------------------------------------

def make_update(
    text: str = "/start",
    user_id: int = 12345,
    chat_id: int = 12345,
) -> MagicMock:
    """Create a mock telegram.Update with all async reply methods.

    The returned mock has ``spec=object`` on leaf nodes to keep it lightweight
    while still providing the attribute hierarchy handlers expect.
    """
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "test_user"
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.chat_id = chat_id
    # Async reply helpers
    update.message.reply_text = AsyncMock()
    update.message.reply_html = AsyncMock()
    update.message.reply_document = AsyncMock()
    update.message.delete = AsyncMock()
    update.message.edit_text = AsyncMock()
    return update


def make_context(user_data: dict | None = None) -> MagicMock:
    """Create a mock telegram.ext ContextTypes.DEFAULT_TYPE."""
    ctx = MagicMock()
    ctx.user_data = user_data if user_data is not None else {}
    ctx.args = []
    ctx.bot.send_message = AsyncMock()
    return ctx


def make_callback_query(
    data: str = "cb_data",
    user_id: int = 12345,
    chat_id: int = 12345,
) -> MagicMock:
    """Create a mock Update with a callback_query (no message.text)."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat.id = chat_id
    update.message = None
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.message.edit_text = AsyncMock()
    update.callback_query.message.reply_text = AsyncMock()
    update.callback_query.message.delete = AsyncMock()
    update.callback_query.message.chat_id = chat_id
    return update
