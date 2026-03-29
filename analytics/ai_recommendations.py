from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from analytics.base import SourceResult, TrendItem
from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1)


def _format_trends_summary(results: list[SourceResult]) -> str:
    parts = []
    for r in results:
        if not r.items or r.source_key == "ai_recommendations":
            continue
        top = r.items[:3]
        lines = [f"  • {i.title} {i.score}".strip() for i in top]
        parts.append(f"{r.source_name}:\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _call_claude(trends_text: str) -> str:
    from bot.services.claude_client import HAIKU, call_claude

    prompt = f"""Ты — эксперт по контент-маркетингу для wellness-специалиста (ароматерапия, звуковые ванны, поющие чаши, ольфактотерапия).

Сегодняшние тренды:
{trends_text}

На основе этих трендов предложи 3 идеи для постов в Instagram или Telegram. Для каждой:
1. 📌 Тема (1 строка)
2. 🪝 Первая строка поста — зацепка для читателя
3. 💡 О чём писать (2-3 тезиса)
4. #️⃣ Хэштеги (3-4)

Отвечай на русском. Будь конкретным, без воды."""

    return call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000, model=HAIKU, context="ai_recommendations",
    )


async def get_ai_recommendations(results: list[SourceResult]) -> SourceResult:
    source = SourceResult(
        source_name="Идеи постов от ИИ",
        source_key="ai_recommendations",
        icon="🤖",
    )

    if not settings.is_source_enabled("ai_recommendations"):
        source.error = "ANTHROPIC_API_KEY не задан"
        return source

    try:
        trends_text = _format_trends_summary(results)
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(_executor, _call_claude, trends_text)
        source.items = [TrendItem(title=text)]
    except Exception as exc:
        logger.warning("AI recommendations error: %s", exc)
        source.error = str(exc)

    return source
