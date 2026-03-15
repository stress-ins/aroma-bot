"""Subscription service — async CRUD + business logic for UserProfile/Subscription/PromoCode/UsageLog."""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db.models import PromoCode, Subscription, UsageLog, UserProfile
from db.session import AsyncSessionLocal

TIER_RANK: dict[str, int] = {"free": 0, "student": 1, "expert": 2}
FREE_DAILY_LIMIT = 10
TRIAL_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_utc() -> str:
    return _now().strftime("%Y-%m-%d")


async def get_or_create_user(telegram_id: int) -> UserProfile:
    """Return existing UserProfile or create a new one with 7-day expert trial."""
    async with AsyncSessionLocal() as session:
        user = await session.get(UserProfile, telegram_id)
        if user is None:
            trial_ends_at = _now() + timedelta(days=TRIAL_DAYS)
            user = UserProfile(
                telegram_id=telegram_id,
                tier="free",
                trial_ends_at=trial_ends_at,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def effective_tier(user: UserProfile) -> str:
    """Return the user's effective tier, considering active trial."""
    if user.trial_ends_at is not None:
        trial_end = user.trial_ends_at
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        if trial_end > _now():
            return "expert"
    return user.tier


async def check_daily_limit(telegram_id: int) -> tuple[int, int]:
    """Return (used_today, max_allowed) for free-tier users."""
    today = _today_utc()
    async with AsyncSessionLocal() as session:
        stmt = select(UsageLog).where(
            UsageLog.telegram_id == telegram_id,
            UsageLog.date == today,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        used = row.cards_created if row else 0
    return used, FREE_DAILY_LIMIT


async def increment_daily_usage(telegram_id: int) -> None:
    """Upsert UsageLog — increment cards_created for today."""
    today = _today_utc()
    async with AsyncSessionLocal() as session:
        stmt = (
            sqlite_insert(UsageLog)
            .values(telegram_id=telegram_id, date=today, cards_created=1)
            .on_conflict_do_update(
                index_elements=["telegram_id", "date"],
                set_={"cards_created": UsageLog.cards_created + 1},
            )
        )
        await session.execute(stmt)
        await session.commit()


async def activate_promo(telegram_id: int, code: str) -> PromoCode | None:
    """
    Validate promo code and apply it to the user.
    Returns the PromoCode on success, None if invalid/expired/exhausted.
    """
    async with AsyncSessionLocal() as session:
        promo = (
            await session.execute(select(PromoCode).where(PromoCode.code == code.upper().strip()))
        ).scalar_one_or_none()

        if promo is None:
            return None
        if promo.uses_count >= promo.max_uses:
            return None
        if promo.expires_at is not None:
            exp = promo.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < _now():
                return None

        now = _now()
        ends_at = now + timedelta(days=promo.duration_days)

        sub = Subscription(
            telegram_id=telegram_id,
            tier=promo.tier,
            starts_at=now,
            ends_at=ends_at,
            promo_code_id=promo.id,
            activated_by="promo",
        )
        session.add(sub)

        promo.uses_count += 1

        user = await session.get(UserProfile, telegram_id)
        if user is None:
            user = UserProfile(
                telegram_id=telegram_id,
                tier=promo.tier,
                trial_ends_at=ends_at,
            )
            session.add(user)
        else:
            user.tier = promo.tier
            user.trial_ends_at = ends_at
            user.updated_at = now

        await session.commit()
        await session.refresh(promo)
        return promo


async def set_subscription(telegram_id: int, tier: str, days: int | None) -> None:
    """Manual subscription activation — admin use."""
    now = _now()
    ends_at = now + timedelta(days=days) if days else None

    async with AsyncSessionLocal() as session:
        sub = Subscription(
            telegram_id=telegram_id,
            tier=tier,
            starts_at=now,
            ends_at=ends_at,
            activated_by="manual",
        )
        session.add(sub)

        user = await session.get(UserProfile, telegram_id)
        if user is None:
            user = UserProfile(
                telegram_id=telegram_id,
                tier=tier,
                trial_ends_at=ends_at,
            )
            session.add(user)
        else:
            user.tier = tier
            user.trial_ends_at = ends_at
            user.updated_at = now

        await session.commit()


async def create_promo_codes(
    tier: str,
    duration_days: int,
    count: int = 1,
    prefix: str = "AROMA",
    max_uses: int = 1,
    expires_at: datetime | None = None,
) -> list[str]:
    """Generate N unique promo codes and save them to DB."""
    codes: list[str] = []
    async with AsyncSessionLocal() as session:
        for _ in range(count):
            while True:
                suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
                code = f"{prefix}-{suffix}"
                existing = (
                    await session.execute(select(PromoCode).where(PromoCode.code == code))
                ).scalar_one_or_none()
                if existing is None:
                    break

            promo = PromoCode(
                code=code,
                tier=tier,
                duration_days=duration_days,
                max_uses=max_uses,
                uses_count=0,
                expires_at=expires_at,
            )
            session.add(promo)
            codes.append(code)

        await session.commit()
    return codes


async def list_promo_codes() -> list[PromoCode]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))
        return list(result.scalars().all())


async def list_users(limit: int = 50, offset: int = 0) -> list[UserProfile]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserProfile).order_by(UserProfile.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
