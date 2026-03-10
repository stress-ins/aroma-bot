from __future__ import annotations

import re

from analytics.base import SourceResult, TrendItem

_ESCAPE_RE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def _esc(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    return _ESCAPE_RE.sub(r"\\\1", text)


def _divider() -> str:
    return "━━━━━━━━━━━━━━━━━━━━━━"


def format_section(result: SourceResult) -> str:
    lines: list[str] = []
    lines.append(_divider())
    lines.append(f"{result.icon} *{_esc(result.source_name)}*")
    lines.append(_divider())

    if not result.ok:
        reason = result.error or "нет данных"
        lines.append(f"_⚠️ {_esc(reason)}_")
        return "\n".join(lines)

    if result.source_key == "google_trends":
        lines.append("🔥 *Растущие запросы:*")
        for item in result.items:
            score_esc = _esc(item.score)
            title_esc = _esc(item.title)
            extra_esc = f" \\({_esc(item.extra)}\\)" if item.extra else ""
            lines.append(f"• {title_esc} *{score_esc}*{extra_esc}")
    elif result.source_key in ("youtube", "youtube_ru"):
        for i, item in enumerate(result.items, 1):
            title_esc = _esc(item.title)
            score_esc = _esc(item.score)
            extra_esc = _esc(item.extra)
            url_esc = _esc(item.url)
            lines.append(f"{i}\\. [{title_esc}]({url_esc})")
            lines.append(f"   {score_esc}")
            if extra_esc:
                lines.append(f"   {extra_esc}")
            if item.summary:
                lines.append(f"   _{_esc(item.summary)}_")
    elif result.source_key in ("tiktok", "tiktok_ru"):
        for i, item in enumerate(result.items, 1):
            title_esc = _esc(item.title[:90])
            score_esc = _esc(item.score)
            extra_esc = _esc(item.extra)
            if item.url:
                lines.append(f"{i}\\. [{title_esc}]({item.url})")
            else:
                lines.append(f"{i}\\. {title_esc}")
            lines.append(f"   {score_esc} | {extra_esc}")
    elif result.source_key in ("reddit", "twitter", "instagram"):
        for item in result.items:
            title_esc = _esc(item.title[:100])
            score_esc = _esc(item.score)
            extra_esc = _esc(item.extra) if item.extra else ""
            if item.url:
                lines.append(f"• [{title_esc}]({item.url}) — {score_esc}")
            else:
                lines.append(f"• {title_esc} — {score_esc}")
            if extra_esc:
                lines.append(f"  {extra_esc}")
    elif result.source_key == "telegram_channels":
        for item in result.items:
            title_esc = _esc(item.title[:100])
            score_esc = _esc(item.score)
            extra_esc = _esc(item.extra)
            if item.url:
                lines.append(f"• [{title_esc}]({item.url})")
            else:
                lines.append(f"• {title_esc}")
            lines.append(f"  {extra_esc}: {score_esc}")
    elif result.source_key == "yandex_news":
        for item in result.items:
            title_esc = _esc(item.title[:100])
            date_esc = _esc(item.extra) if item.extra else ""
            if item.url:
                lines.append(f"• [{title_esc}]({item.url})" + (f" _{date_esc}_" if date_esc else ""))
            else:
                lines.append(f"• {title_esc}")
    elif result.source_key == "wordstat":
        lines.append("🔥 *Поисковые объёмы \\(Яндекс\\):*")
        for item in result.items:
            title_esc = _esc(item.title)
            score_esc = _esc(item.score)
            extra_esc = f" {_esc(item.extra)}" if item.extra else ""
            lines.append(f"• {title_esc} — *{score_esc}*{extra_esc}")
    elif result.source_key == "vk":
        for item in result.items:
            title_esc = _esc(item.title[:100])
            score_esc = _esc(item.score)
            if item.url:
                lines.append(f"• [{title_esc}]({item.url}) — {score_esc}")
            else:
                lines.append(f"• {title_esc} — {score_esc}")
    elif result.source_key == "ai_recommendations":
        if result.items:
            lines.append(_esc(result.items[0].title))
    else:
        for item in result.items:
            lines.append(f"• {_esc(item.title)} — {_esc(item.score)}")

    return "\n".join(lines)
