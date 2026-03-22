"""Trend Card Generator: produces structured trend cards from intelligence report."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def generate_cards_from_report_sync(report: dict) -> list[dict]:
    """Convert trend intelligence report opportunities into structured cards.

    Each card has: card_id, keyword, title, strength, lifecycle, sentiment,
    summary, recommendation, suggested_formats, velocity, convergence.
    """
    from bot.services.claude_client import call_claude

    opportunities = report.get("top_opportunities", [])
    if not opportunities:
        return []

    # Format opportunities for Claude
    opp_text = []
    for i, opp in enumerate(opportunities[:10], 1):
        opp_text.append(
            f"{i}. keyword={opp.get('keyword', '')}, score={opp.get('score', 0):.2f}, "
            f"velocity={opp.get('velocity', 0):.2f}, lifecycle={opp.get('lifecycle', '')}, "
            f"sentiment={opp.get('sentiment', '')}, angle={opp.get('content_angle', '')}"
        )

    prompt = f"""\
Ты контент-стратег для бренда ароматерапии/wellness. На основе трендов создай карточки.

Тренды:
{chr(10).join(opp_text)}

Для каждого тренда создай карточку:
CARD {'{N}'}:
TITLE: [заголовок 5-10 слов, привлекательный]
SUMMARY: [2-3 предложения: что за тренд, почему важен]
RECOMMENDATION: [1-2 предложения: что Aromara может сделать]
FORMATS: [через запятую: instagram, carousel, reels, threads_series]

Создай карточки для топ-5 трендов."""

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
        context="trend_card_generator",
    )

    cards = _parse_cards(raw, opportunities)
    return cards


def _parse_cards(raw: str, opportunities: list[dict]) -> list[dict]:
    """Parse Claude response into card dicts."""
    cards = []
    current = None
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        m = re.match(r"CARD\s+(\d+)", line, re.IGNORECASE)
        if m:
            if current:
                cards.append(current)
            idx = int(m.group(1)) - 1
            opp = opportunities[idx] if idx < len(opportunities) else {}
            current = {
                "card_id": uuid.uuid4().hex[:12],
                "keyword": opp.get("keyword", ""),
                "strength": opp.get("score", 0.5),
                "lifecycle": opp.get("lifecycle", ""),
                "sentiment": opp.get("sentiment", ""),
                "velocity": opp.get("velocity", 0),
                "convergence": opp.get("convergence", 0),
                "title": "",
                "summary": "",
                "recommendation": "",
                "suggested_formats": [],
                "source_signals": opp.get("sources", []),
                "expires_at": expires.isoformat(),
            }
            continue

        if current is None:
            continue

        cleaned = line.replace("**", "").strip()
        if cleaned.upper().startswith("TITLE:"):
            current["title"] = cleaned.split(":", 1)[1].strip()
        elif cleaned.upper().startswith("SUMMARY:"):
            current["summary"] = cleaned.split(":", 1)[1].strip()
        elif cleaned.upper().startswith("RECOMMENDATION:"):
            current["recommendation"] = cleaned.split(":", 1)[1].strip()
        elif cleaned.upper().startswith("FORMATS:"):
            formats_raw = cleaned.split(":", 1)[1].strip()
            current["suggested_formats"] = [f.strip() for f in formats_raw.split(",") if f.strip()]

    if current:
        cards.append(current)

    # Fill titles for cards without Claude-generated ones
    for card in cards:
        if not card["title"]:
            card["title"] = card["keyword"].capitalize() if card["keyword"] else "Trend"

    return cards[:5]


async def generate_and_save_cards(team_id: str | None = None) -> list[dict]:
    """Generate trend cards and save to DB."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import select

    from db.models import TrendCardModel
    from db.session import AsyncSessionLocal

    # Get trend report
    try:
        from analytics.trend_intelligence import generate_trend_report
        report = await generate_trend_report()
    except Exception:
        logger.error("Failed to generate trend report", exc_info=True)
        return []

    if not report.get("top_opportunities"):
        return []

    # Generate cards via Claude
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    cards = await loop.run_in_executor(executor, generate_cards_from_report_sync, report)

    if not cards:
        return []

    # Save to DB
    async with AsyncSessionLocal() as session:
        for card_data in cards:
            expires_at = None
            if card_data.get("expires_at"):
                try:
                    expires_at = datetime.fromisoformat(card_data["expires_at"])
                except (ValueError, TypeError):
                    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

            model = TrendCardModel(
                card_id=card_data["card_id"],
                team_id=team_id,
                keyword=card_data.get("keyword", ""),
                title=card_data.get("title", ""),
                strength=card_data.get("strength", 0),
                lifecycle=card_data.get("lifecycle", ""),
                sentiment=card_data.get("sentiment", ""),
                summary=card_data.get("summary", ""),
                recommendation=card_data.get("recommendation", ""),
                suggested_formats=card_data.get("suggested_formats", []),
                source_signals=card_data.get("source_signals", []),
                velocity=card_data.get("velocity", 0),
                convergence=card_data.get("convergence", 0),
                expires_at=expires_at,
            )
            session.add(model)
        await session.commit()

    return cards
