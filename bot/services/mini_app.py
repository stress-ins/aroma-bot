from __future__ import annotations

from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import settings


def mini_app_base_url() -> str:
    return settings.mini_app_url.strip().rstrip("/")


def mini_app_available() -> bool:
    return bool(mini_app_base_url())


def build_mini_app_url(*, draft_id: str | None = None, tab: str | None = None) -> str:
    base = mini_app_base_url()
    if not base:
        return ""

    params: dict[str, str] = {}
    if draft_id:
        params["draft_id"] = draft_id
    if tab:
        params["tab"] = tab

    if not params:
        return base
    return f"{base}?{urlencode(params)}"


def build_mini_app_markup(
    *,
    label: str = "🧭 Mini App",
    draft_id: str | None = None,
    tab: str | None = None,
) -> InlineKeyboardMarkup | None:
    url = build_mini_app_url(draft_id=draft_id, tab=tab)
    if not url:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, web_app=WebAppInfo(url=url)),
    ]])


def append_mini_app_button(
    markup: InlineKeyboardMarkup | None,
    *,
    label: str = "🧭 Mini App",
    draft_id: str | None = None,
    tab: str | None = None,
) -> InlineKeyboardMarkup | None:
    extra = build_mini_app_markup(label=label, draft_id=draft_id, tab=tab)
    if extra is None:
        return markup
    if markup is None:
        return extra

    rows = [list(row) for row in markup.inline_keyboard]
    rows.extend(extra.inline_keyboard)
    return InlineKeyboardMarkup(rows)
