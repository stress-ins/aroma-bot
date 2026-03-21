"""Detect Instagram / Threads links in messages and offer monitoring actions."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from bot.services.brand_settings_store import get_brand_settings, update_brand_settings
from bot.services.oembed import extract_hashtags, fetch_instagram_caption, fetch_threads_caption
from bot.services.team_store import get_default_team

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------

_INSTAGRAM_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:"
    r"(?P<ig_type>p|reel|reels)/(?P<ig_code>[\w-]+)"
    r"|"
    r"(?P<ig_user>[A-Za-z0-9_.]{1,30})"
    r")"
    r"/?(?:\?[^ ]*)?"
    r"(?=\s|$|[)\].,!?;])",
    re.IGNORECASE,
)

_THREADS_RE = re.compile(
    r"https?://(?:www\.)?threads\.net/"
    r"@(?P<th_user>[A-Za-z0-9_.]{1,30})"
    r"(?:/post/(?P<th_post>[A-Za-z0-9_-]+))?"
    r"/?(?:\?[^ ]*)?"
    r"(?=\s|$|[)\].,!?;])",
    re.IGNORECASE,
)

# Instagram reserved paths that are NOT usernames
_IG_RESERVED = frozenset({
    "explore", "accounts", "about", "stories", "direct",
    "developer", "legal", "privacy", "terms", "session",
    "emails", "challenge", "nux", "push", "api",
})

_MAX_ACCOUNTS_PER_PLATFORM = 20
_MAX_HASHTAGS = 30


@dataclass
class ParsedLink:
    platform: str       # "instagram" | "threads"
    link_type: str      # "profile" | "post"
    username: str | None
    shortcode: str | None
    url: str


def parse_social_links(text: str) -> list[ParsedLink]:
    """Extract social links from arbitrary text. Returns list (usually 0-1 items)."""
    results: list[ParsedLink] = []

    for m in _INSTAGRAM_RE.finditer(text):
        if m.group("ig_type"):
            results.append(ParsedLink(
                platform="instagram",
                link_type="post",
                username=None,
                shortcode=m.group("ig_code"),
                url=m.group(0),
            ))
        else:
            user = m.group("ig_user")
            if user and user.lower() not in _IG_RESERVED:
                results.append(ParsedLink(
                    platform="instagram",
                    link_type="profile",
                    username=user,
                    shortcode=None,
                    url=m.group(0),
                ))

    for m in _THREADS_RE.finditer(text):
        if m.group("th_post"):
            results.append(ParsedLink(
                platform="threads",
                link_type="post",
                username=m.group("th_user"),
                shortcode=m.group("th_post"),
                url=m.group(0),
            ))
        else:
            results.append(ParsedLink(
                platform="threads",
                link_type="profile",
                username=m.group("th_user"),
                shortcode=None,
                url=m.group(0),
            ))

    return results


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------


async def _handle_social_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip() if update.message else ""
    if not text:
        return

    links = parse_social_links(text)
    if not links:
        return

    link = links[0]  # process only the first link

    user = update.effective_user
    if not user:
        return
    team = await get_default_team(user.id, user.username or "")
    bs = await get_brand_settings(team.team_id)

    if link.link_type == "profile":
        await _handle_profile(update, link, bs)
    else:
        await _handle_post(update, context, link, bs, team.team_id)


async def _handle_profile(
    update: Update,
    link: ParsedLink,
    bs,
) -> None:
    username = link.username
    platform = link.platform
    platform_label = "Instagram" if platform == "instagram" else "Threads"

    field = f"{platform}_accounts"
    accounts: list = getattr(bs, field, None) or []

    # Already monitored?
    if any(a.get("username", "").lower() == username.lower() for a in accounts):
        await update.message.reply_text(
            f"@{username} ({platform_label}) уже на мониторинге."
        )
        return

    # Limit check
    if len(accounts) >= _MAX_ACCOUNTS_PER_PLATFORM:
        await update.message.reply_text(
            f"Достигнут лимит ({_MAX_ACCOUNTS_PER_PLATFORM}) аккаунтов для {platform_label}."
        )
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Добавить @{username} на мониторинг",
                callback_data=f"link:aa:{_PLATFORM_SHORT[platform]}:{username}",
            ),
        ],
        [InlineKeyboardButton("Отмена", callback_data="link:x")],
    ])
    await update.message.reply_text(
        f"Профиль @{username} ({platform_label})",
        reply_markup=keyboard,
    )


async def _handle_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    link: ParsedLink,
    bs,
    team_id: str,
) -> None:
    platform_label = "Instagram" if link.platform == "instagram" else "Threads"

    # Fetch caption via oEmbed
    if link.platform == "instagram":
        caption = await fetch_instagram_caption(link.url)
    else:
        caption = await fetch_threads_caption(link.url)

    hashtags: list[str] = []
    if caption:
        hashtags = extract_hashtags(caption)

    # Filter out already tracked
    existing = set((t.lower() for t in (bs.tracked_hashtags or [])))
    new_tags = [t for t in hashtags if t not in existing]

    rows: list[list[InlineKeyboardButton]] = []
    lines: list[str] = []

    author = f" @{link.username}" if link.username else ""
    lines.append(f"Пост{author} ({platform_label})")

    if new_tags:
        tag_display = " ".join(f"#{t}" for t in new_tags)
        lines.append(f"\nНайдены хештеги: {tag_display}")

        # Store tags in user_data for the "add all" callback
        context.user_data["_link_tags"] = new_tags

        if len(new_tags) > 1:
            rows.append([InlineKeyboardButton(
                f"Добавить все {len(new_tags)} хештегов",
                callback_data="link:aat",
            )])
        else:
            rows.append([InlineKeyboardButton(
                f"Добавить #{new_tags[0]}",
                callback_data=f"link:at:{new_tags[0]}",
            )])
    elif hashtags and not new_tags:
        lines.append("\nВсе найденные хештеги уже отслеживаются.")
    else:
        lines.append("\nХештеги не найдены.")

    # Offer to add author to monitoring (if username available)
    if link.username:
        field = f"{link.platform}_accounts"
        accounts: list = getattr(bs, field, None) or []
        already = any(a.get("username", "").lower() == link.username.lower() for a in accounts)
        if not already and len(accounts) < _MAX_ACCOUNTS_PER_PLATFORM:
            rows.append([InlineKeyboardButton(
                f"Добавить @{link.username} на мониторинг",
                callback_data=f"link:aa:{_PLATFORM_SHORT[link.platform]}:{link.username}",
            )])

    rows.append([InlineKeyboardButton("Отмена", callback_data="link:x")])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(rows),
    )


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------

_PLATFORM_SHORT = {"instagram": "ig", "threads": "th"}
_PLATFORM_MAP = {"ig": "instagram", "th": "threads"}
_PLATFORM_LABEL = {"ig": "Instagram", "th": "Threads"}


async def _cb_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    logger.info("link_detector cb_add_account: data=%s", query.data)

    try:
        # link:aa:{pl}:{username}
        parts = query.data.split(":", 3)
        if len(parts) < 4:
            logger.warning("link_detector: bad callback data: %s", query.data)
            return
        pl_short, username = parts[2], parts[3]
        platform = _PLATFORM_MAP.get(pl_short)
        if not platform:
            logger.warning("link_detector: unknown platform: %s", pl_short)
            return

        user = update.effective_user
        if not user:
            return
        team = await get_default_team(user.id, user.username or "")
        bs = await get_brand_settings(team.team_id)

        field = f"{platform}_accounts"
        accounts: list = list(getattr(bs, field, None) or [])

        if any(a.get("username", "").lower() == username.lower() for a in accounts):
            await query.edit_message_text(f"@{username} уже на мониторинге.")
            return

        if len(accounts) >= _MAX_ACCOUNTS_PER_PLATFORM:
            await query.edit_message_text(
                f"Лимит ({_MAX_ACCOUNTS_PER_PLATFORM}) аккаунтов достигнут."
            )
            return

        accounts.append({"username": username, "status": "checking"})
        await update_brand_settings(team.team_id, **{field: accounts})

        label = _PLATFORM_LABEL.get(pl_short, platform)
        await query.edit_message_text(f"@{username} ({label}) добавлен на мониторинг.")
    except Exception:
        logger.exception("link_detector cb_add_account failed")
        await query.edit_message_text("Ошибка при добавлении аккаунта.")


async def _cb_add_tag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    logger.info("link_detector cb_add_tag: data=%s", query.data)

    try:
        # link:at:{tag}
        parts = query.data.split(":", 2)
        if len(parts) < 3:
            return
        tag = parts[2].lower()

        user = update.effective_user
        if not user:
            return
        team = await get_default_team(user.id, user.username or "")
        bs = await get_brand_settings(team.team_id)

        tracked: list[str] = list(bs.tracked_hashtags or [])
        if tag in [t.lower() for t in tracked]:
            await query.edit_message_text(f"#{tag} уже отслеживается.")
            return
        if len(tracked) >= _MAX_HASHTAGS:
            await query.edit_message_text(f"Лимит ({_MAX_HASHTAGS}) хештегов достигнут.")
            return

        tracked.append(tag)
        await update_brand_settings(team.team_id, tracked_hashtags=tracked)
        await query.edit_message_text(f"#{tag} добавлен в отслеживаемые хештеги.")
    except Exception:
        logger.exception("link_detector cb_add_tag failed")
        await query.edit_message_text("Ошибка при добавлении хештега.")


async def _cb_add_all_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    logger.info("link_detector cb_add_all_tags: data=%s", query.data)

    try:
        tags: list[str] = context.user_data.get("_link_tags", [])
        if not tags:
            await query.edit_message_text("Хештеги не найдены.")
            return

        user = update.effective_user
        if not user:
            return
        team = await get_default_team(user.id, user.username or "")
        bs = await get_brand_settings(team.team_id)

        tracked: list[str] = list(bs.tracked_hashtags or [])
        existing = set(t.lower() for t in tracked)
        added: list[str] = []
        for tag in tags:
            if tag not in existing and len(tracked) < _MAX_HASHTAGS:
                tracked.append(tag)
                existing.add(tag)
                added.append(tag)

        if added:
            await update_brand_settings(team.team_id, tracked_hashtags=tracked)
            display = " ".join(f"#{t}" for t in added)
            await query.edit_message_text(f"Добавлены хештеги: {display}")
        else:
            await query.edit_message_text("Все хештеги уже отслеживаются.")
    except Exception:
        logger.exception("link_detector cb_add_all_tags failed")
        await query.edit_message_text("Ошибка при добавлении хештегов.")


async def _cb_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    logger.info("link_detector cb_cancel")
    await query.edit_message_text("Отменено.")


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_link_detector_handlers():
    """Return handlers for link detection. MessageHandler goes to group 4."""
    return [
        MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_social_link),
        CallbackQueryHandler(_cb_add_account, pattern=r"^link:aa:"),
        CallbackQueryHandler(_cb_add_tag, pattern=r"^link:at:"),
        CallbackQueryHandler(_cb_add_all_tags, pattern=r"^link:aat$"),
        CallbackQueryHandler(_cb_cancel, pattern=r"^link:x$"),
    ]
