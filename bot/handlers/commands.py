from __future__ import annotations

import logging
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler

from config import settings

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "🌿 *Aroma Trends Bot*\n\n"
    "Я слежу за трендами в ароматерапии, регуляции нервной системы, "
    "медитациях, гонге и сенсорных практиках\\.\n\n"
    "Каждое утро я присылаю дайджест с горячими темами из Google Trends, "
    "YouTube, Reddit и других источников\\.\n\n"
    "*/trends* — получить аналитику прямо сейчас\n"
    "*/content* — агентный контент\\: цель → формат → тема → готовый материал\n"
    "*/threads* — темы постов для Threads \\+ пост \\+ картинка\n"
    "*/carousel* — карусель из 5 слайдов \\+ картинки\n"
    "*/status* — какие источники активны\n"
    "*/help* — список команд"
)

HELP_TEXT = (
    "📋 *Команды бота:*\n\n"
    "*/trends* — аналитика прямо сейчас \\(🇷🇺 \\+ 🇬🇧\\)\n"
    "*/content* — универсальный агентный флоу для контента в соцсетях\n"
    "*/threads* — темы постов для Threads \\+ пост \\+ картинка\n"
    "*/carousel* — карусель из 5 слайдов \\+ картинки\n"
    "*/keywords* — просмотр и редактирование ключевых слов\n"
    "*/status* — проверить источники данных\n"
    "*/start* — приветствие\n"
    "*/help* — эта справка"
)

SOURCE_LABELS = {
    "google_trends_en": "📈 Google Trends EN",
    "google_trends_ru": "📈 Google Trends RU",
    "youtube": "▶️ YouTube",
    "reddit": "💬 Reddit",
    "telegram_channels": "📱 Telegram каналы",
    "twitter": "🐦 Twitter/X",
    "instagram": "📸 Instagram",
    "vk": "🔵 ВКонтакте",
    "ai_recommendations": "🤖 Рекомендации ИИ",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        HELP_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def trends(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from analytics.aggregator import collect_all
    from formatters.report import build_report
    from cache.store import cache

    msg = await update.message.reply_text("⏳ Собираю данные, подожди немного...")

    cached = cache.get("digest")
    if cached:
        ru_report, en_report = cached
    else:
        results = await collect_all()
        ru_report = build_report(results, lang="ru")
        en_report = build_report(results, lang="en")
        cache.set("digest", (ru_report, en_report))
        cache.set("results", results)

    await msg.delete()
    for report in (ru_report, en_report):
        for chunk in _split_message(report, 4096):
            try:
                await update.message.reply_text(
                    chunk,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True,
                )
            except Exception:
                plain = chunk.replace("\\", "")
                await update.message.reply_text(plain, disable_web_page_preview=True)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🖼 Обложки YouTube", callback_data="yt_thumbs"),
    ]])
    await update.message.reply_text("📸 Топ видео YouTube:", reply_markup=keyboard)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sources = ["google_trends_ru", "google_trends_en", "youtube", "reddit",
               "telegram_channels", "twitter", "instagram", "vk", "ai_recommendations"]
    lines = ["⚙️ *Статус источников:*\n"]
    for src in sources:
        enabled = settings.is_source_enabled(src)
        icon = "✅" if enabled else "❌"
        label = SOURCE_LABELS.get(src, src)
        lines.append(f"{icon} {label}")

    digest_time = settings.daily_digest_time.replace("-", "\\-")
    tz = settings.timezone.replace("/", "\\/")
    lines.append(f"\n⏰ Дайджест: *{digest_time}* \\({tz}\\)")

    text = "\n".join(lines)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


def _video_id(url: str) -> str:
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else ""


def _thumb_url(video_id: str) -> str:
    return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"


async def yt_thumbs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from cache.store import cache

    query = update.callback_query
    await query.answer()

    results = cache.get("results")
    if not results:
        await query.message.reply_text("⚠️ Данные устарели, запросите /trends снова.")
        return

    media: list[InputMediaPhoto] = []
    for result in results:
        if result.source_key not in ("youtube", "youtube_ru"):
            continue
        for i, item in enumerate(result.items[:5]):
            vid_id = _video_id(item.url)
            if not vid_id:
                continue
            caption = f"{'🇬🇧' if result.source_key == 'youtube' else '🇷🇺'} {i+1}. {item.title[:80]}\n{item.score}"
            media.append(InputMediaPhoto(media=_thumb_url(vid_id), caption=caption))

    if not media:
        await query.message.reply_text("⚠️ Видео не найдены в кэше.")
        return

    # Telegram media group limit = 10
    for i in range(0, len(media), 10):
        await query.message.reply_media_group(media[i:i+10])


def _split_message(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
