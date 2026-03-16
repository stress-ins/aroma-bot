"""Daily Oil of the Day — selection, caching, and notification service."""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.models import AromaCardModel, DailyOilModel, UserProfile
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 30


async def select_daily_oil(target_date: str) -> DailyOilModel:
    """Pick aroma not used in the last 30 days, generate fact+practice via Claude Haiku.

    If a row for *target_date* already exists it is returned unchanged.
    """
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(
                select(DailyOilModel).where(DailyOilModel.date == target_date)
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        # Recently used slugs (last 30 days)
        cutoff = (
            datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=_LOOKBACK_DAYS)
        ).strftime("%Y-%m-%d")
        recent_rows = (
            await session.execute(
                select(DailyOilModel.slug).where(DailyOilModel.date >= cutoff)
            )
        ).scalars().all()
        recent_slugs = set(recent_rows)

        # All aroma cards
        all_aromas = (
            await session.execute(
                select(AromaCardModel).where(AromaCardModel.category == "aroma")
            )
        ).scalars().all()

        candidates = [a for a in all_aromas if a.slug not in recent_slugs]
        if not candidates:
            candidates = list(all_aromas)
        if not candidates:
            raise RuntimeError("No aroma cards in the database")

        chosen = random.choice(candidates)

        # Generate fact and daily practice via Claude Haiku
        fact, practice = _generate_fact_and_practice(chosen.name)

        row = DailyOilModel(
            date=target_date,
            slug=chosen.slug,
            name=chosen.name,
            fact=fact,
            daily_practice=practice,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


def _generate_fact_and_practice(oil_name: str) -> tuple[str, str]:
    """Call Claude Haiku to get a fun fact and daily practice for the oil."""
    from bot.services.claude_client import HAIKU, call_claude

    prompt = (
        f'Ты — эксперт по ароматерапии. Для эфирного масла "{oil_name}" дай:\n'
        "1. Интересный факт (1-2 предложения)\n"
        "2. Простую практику на день с этим маслом (2-3 предложения)\n\n"
        'Ответ строго в JSON: {{"fact": "...", "daily_practice": "..."}}\n'
        "Без markdown, только JSON."
    )

    try:
        raw = call_claude(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            model=HAIKU,
            context="daily_oil",
        )
        data = json.loads(raw)
        return data.get("fact", ""), data.get("daily_practice", "")
    except Exception as exc:
        logger.warning("Claude daily-oil generation failed: %s", exc)
        return "", ""


async def get_daily_oil(target_date: str | None = None) -> dict | None:
    """Return today's daily oil card as a dict, or None."""
    if target_date is None:
        target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(DailyOilModel).where(DailyOilModel.date == target_date)
            )
        ).scalar_one_or_none()
        if not row:
            return None
        return {
            "date": row.date,
            "slug": row.slug,
            "name": row.name,
            "fact": row.fact,
            "daily_practice": row.daily_practice,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        }


async def get_subscribed_user_ids() -> list[int]:
    """Return telegram_ids of users with daily_oil_subscribed=True."""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(UserProfile.telegram_id).where(
                    UserProfile.daily_oil_subscribed == True  # noqa: E712
                )
            )
        ).scalars().all()
        return list(rows)


async def send_daily_oil_notifications(app) -> None:
    """Send daily oil message to each subscribed user."""
    oil = await get_daily_oil()
    if not oil:
        logger.warning("No daily oil to send")
        return

    user_ids = await get_subscribed_user_ids()
    if not user_ids:
        logger.info("No subscribers for daily oil")
        return

    text = (
        f"\U0001f33f <b>Масло дня — {oil['name']}</b>\n\n"
        f"{oil['fact']}\n\n"
        f"\U0001f9d8 <b>Практика дня:</b>\n{oil['daily_practice']}"
    )

    sent = 0
    for uid in user_ids:
        try:
            await app.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            sent += 1
        except Exception as exc:
            logger.debug("Failed to send daily oil to %s: %s", uid, exc)

    # Mark as sent
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(DailyOilModel).where(DailyOilModel.date == oil["date"])
            )
        ).scalar_one_or_none()
        if row:
            row.sent_at = now
            await session.commit()

    logger.info("Daily oil sent to %d/%d subscribers", sent, len(user_ids))


async def toggle_subscription(telegram_id: int) -> bool:
    """Toggle daily_oil_subscribed flag. Returns new value."""
    async with AsyncSessionLocal() as session:
        user = await session.get(UserProfile, telegram_id)
        if not user:
            return True  # no profile yet — default is subscribed
        user.daily_oil_subscribed = not user.daily_oil_subscribed
        await session.commit()
        return user.daily_oil_subscribed
