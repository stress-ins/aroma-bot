from __future__ import annotations

from datetime import datetime

from analytics.base import SourceResult
from formatters.sections import format_section, _esc
from keywords.registry import ALL_HASHTAGS_EN, ALL_HASHTAGS_RU
from config import settings

# Which source_keys belong to which report
RU_SOURCE_KEYS = {"google_trends_ru", "youtube_ru", "instagram_ru", "vk", "telegram_channels", "ai_recommendations", "wordstat", "tiktok_ru"}
EN_SOURCE_KEYS = {"google_trends_en", "youtube", "reddit", "instagram", "twitter", "tiktok", "threads"}

_RU_MONTHS = {
    "January": "января", "February": "февраля", "March": "марта",
    "April": "апреля", "May": "мая", "June": "июня",
    "July": "июля", "August": "августа", "September": "сентября",
    "October": "октября", "November": "ноября", "December": "декабря",
}


def _date_str(now: datetime) -> str:
    s = now.strftime("%d %B %Y").lstrip("0")
    for en, ru in _RU_MONTHS.items():
        s = s.replace(en, ru)
    return s


def build_report(results: list[SourceResult], lang: str = "ru",
                 now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now()

    date = _esc(_date_str(now))
    source_keys = RU_SOURCE_KEYS if lang == "ru" else EN_SOURCE_KEYS
    flag = "🇷🇺" if lang == "ru" else "🇬🇧"
    label = "Русскоязычные тренды" if lang == "ru" else "English Trends"

    lines: list[str] = [
        f"{flag} *Aroma Trends \\| {label} \\| {date}*",
        "",
    ]

    for result in results:
        if result.source_key not in source_keys:
            continue
        if not settings.is_source_enabled(result.source_key):
            continue
        if not result.ok:
            continue
        lines.append(format_section(result))
        lines.append("")

    # Hashtag footer
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🏷 *Топ хэштеги*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    if lang == "ru":
        tags = ALL_HASHTAGS_RU[:5]
    else:
        tags = ALL_HASHTAGS_EN[:5]
    lines.append(" ".join(_esc(h) for h in tags))

    return "\n".join(lines)
