"""Tests for subscription service — tier checks, promo activation, daily limits."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _make_user(tier="free", trial_ends_at=None):
    from db.models import UserProfile
    user = MagicMock(spec=UserProfile)
    user.telegram_id = 12345
    user.tier = tier
    user.trial_ends_at = trial_ends_at
    return user


class TestEffectiveTier:
    @pytest.mark.asyncio
    async def test_free_tier_without_trial(self):
        from bot.services.subscription_store import effective_tier
        user = _make_user(tier="free", trial_ends_at=None)
        result = await effective_tier(user)
        assert result == "free"

    @pytest.mark.asyncio
    async def test_active_trial_returns_expert(self):
        from bot.services.subscription_store import effective_tier
        future = datetime.now(timezone.utc) + timedelta(days=3)
        user = _make_user(tier="free", trial_ends_at=future)
        result = await effective_tier(user)
        assert result == "expert"

    @pytest.mark.asyncio
    async def test_expired_trial_returns_base_tier(self):
        from bot.services.subscription_store import effective_tier
        past = datetime.now(timezone.utc) - timedelta(days=1)
        user = _make_user(tier="free", trial_ends_at=past)
        result = await effective_tier(user)
        assert result == "free"

    @pytest.mark.asyncio
    async def test_student_tier_without_trial(self):
        from bot.services.subscription_store import effective_tier
        user = _make_user(tier="student", trial_ends_at=None)
        result = await effective_tier(user)
        assert result == "student"

    @pytest.mark.asyncio
    async def test_expert_with_active_trial(self):
        from bot.services.subscription_store import effective_tier
        future = datetime.now(timezone.utc) + timedelta(days=5)
        user = _make_user(tier="expert", trial_ends_at=future)
        result = await effective_tier(user)
        assert result == "expert"

    @pytest.mark.asyncio
    async def test_naive_trial_ends_at_treated_as_utc(self):
        from bot.services.subscription_store import effective_tier
        # Naive datetime (no tzinfo) should still work
        future_naive = datetime.now(timezone.utc) + timedelta(days=2)
        future_naive = future_naive.replace(tzinfo=None)
        user = _make_user(tier="free", trial_ends_at=future_naive)
        result = await effective_tier(user)
        assert result == "expert"


class TestTierRank:
    def test_tier_order(self):
        from bot.services.subscription_store import TIER_RANK
        assert TIER_RANK["free"] < TIER_RANK["student"] < TIER_RANK["expert"]


class TestPromoActivation:
    @pytest.mark.asyncio
    async def test_activate_valid_promo(self):
        from bot.services.subscription_store import activate_promo
        from db.models import PromoCode, UserProfile

        mock_promo = MagicMock(spec=PromoCode)
        mock_promo.id = 1
        mock_promo.code = "AROMA-TEST1"
        mock_promo.tier = "expert"
        mock_promo.duration_days = 30
        mock_promo.max_uses = 5
        mock_promo.uses_count = 0
        mock_promo.expires_at = None

        mock_user = MagicMock(spec=UserProfile)
        mock_user.tier = "free"

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_promo)
        mock_session.get = AsyncMock(return_value=mock_user)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.refresh = AsyncMock()

        with patch("bot.services.subscription_store.AsyncSessionLocal", return_value=mock_session):
            result = await activate_promo(12345, "AROMA-TEST1")

        assert result is mock_promo
        assert mock_promo.uses_count == 1

    @pytest.mark.asyncio
    async def test_activate_exhausted_promo_returns_none(self):
        from bot.services.subscription_store import activate_promo
        from db.models import PromoCode

        mock_promo = MagicMock(spec=PromoCode)
        mock_promo.max_uses = 1
        mock_promo.uses_count = 1
        mock_promo.expires_at = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_promo)

        with patch("bot.services.subscription_store.AsyncSessionLocal", return_value=mock_session):
            result = await activate_promo(12345, "AROMA-USED")

        assert result is None

    @pytest.mark.asyncio
    async def test_activate_expired_promo_returns_none(self):
        from bot.services.subscription_store import activate_promo
        from db.models import PromoCode

        past = datetime.now(timezone.utc) - timedelta(days=1)
        mock_promo = MagicMock(spec=PromoCode)
        mock_promo.max_uses = 10
        mock_promo.uses_count = 0
        mock_promo.expires_at = past

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_promo)

        with patch("bot.services.subscription_store.AsyncSessionLocal", return_value=mock_session):
            result = await activate_promo(12345, "AROMA-EXP")

        assert result is None

    @pytest.mark.asyncio
    async def test_activate_unknown_code_returns_none(self):
        from bot.services.subscription_store import activate_promo

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        with patch("bot.services.subscription_store.AsyncSessionLocal", return_value=mock_session):
            result = await activate_promo(12345, "UNKNOWN")

        assert result is None


class TestDailyLimit:
    @pytest.mark.asyncio
    async def test_check_daily_limit_no_usage(self):
        from bot.services.subscription_store import check_daily_limit

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        with patch("bot.services.subscription_store.AsyncSessionLocal", return_value=mock_session):
            used, max_allowed = await check_daily_limit(12345)

        assert used == 0
        assert max_allowed == 10

    @pytest.mark.asyncio
    async def test_check_daily_limit_with_usage(self):
        from bot.services.subscription_store import check_daily_limit
        from db.models import UsageLog

        mock_log = MagicMock(spec=UsageLog)
        mock_log.cards_created = 7

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_log)

        with patch("bot.services.subscription_store.AsyncSessionLocal", return_value=mock_session):
            used, max_allowed = await check_daily_limit(12345)

        assert used == 7
        assert max_allowed == 10
