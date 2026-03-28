"""Centralised brand-settings store (SQLite, per-team).

Backward compatible: callers without team_id get the global/default settings row.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from db.session import AsyncSessionLocal
from db.models import BrandSettingsModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults — seeded on first access when the table is empty.
# ---------------------------------------------------------------------------

_DEFAULT_BRAND_VOICE = (
    "Ты — контент-стратег специалиста по регуляции нервной системы через "
    "сенсорные практики (ароматерапия, медитации, гонг).\n\n"
    "Аудитория: люди с перегрузкой и стрессом + компании для wellbeing-программ.\n"
    "Голос: спокойный, ясный, экспертный. Без инфоцыганства и псевдомедицинских обещаний.\n"
    "Цели контента: доверие, вовлечение, продажи, демонстрация экспертности."
)

_DEFAULT_FORBIDDEN_PHRASES: list[str] = [
    "тазовая волна",
    "занимать место без извинений",
    "боимся быть слишком много",
    "на волне контроля",
    "минуя фильтры",
    "мы сжимаем живот",
    "запах попадает прямо в мозг",
    "чувствовать без стены",
    "надо быть острым",
    "просто стой",
    "погружаясь в",
    "исследуя",
    "позволь себе",
    "мощный инструмент",
    "невероятный результат",
    "текстуру своего дыхания",
    "интегрировать",
    "ресурсное состояние",
    "не подменяя сексуальностью",
]

_DEFAULT_TARGET_PLATFORMS: list[str] = ["threads", "instagram", "telegram"]

# ---------------------------------------------------------------------------
# Module-level cache for sync access from agents running in run_in_executor.
# Dict keyed by team_id (None = global/default).
# ---------------------------------------------------------------------------

_cache: dict[str | None, BrandSettingsModel] = {}


class BrandSettingsNotLoaded(RuntimeError):
    """Raised when get_brand_settings_cached() is called before preload."""


# ---------------------------------------------------------------------------
# Async API
# ---------------------------------------------------------------------------


def _build_default_row(team_id: str | None = None) -> BrandSettingsModel:
    return BrandSettingsModel(
        team_id=team_id,
        brand_voice=_DEFAULT_BRAND_VOICE,
        forbidden_phrases=list(_DEFAULT_FORBIDDEN_PHRASES),
        base_instructions="",
        target_platforms=list(_DEFAULT_TARGET_PLATFORMS),
        updated_at=datetime.now(timezone.utc),
    )


async def get_brand_settings(team_id: str | None = None) -> BrandSettingsModel:
    """Return brand settings for team_id, creating defaults if absent.

    Pass team_id=None to get the global/default settings (backward compat).
    """
    async with AsyncSessionLocal() as session:
        if team_id:
            result = await session.execute(
                select(BrandSettingsModel).where(BrandSettingsModel.team_id == team_id)
            )
        else:
            result = await session.execute(
                select(BrandSettingsModel)
                .where(BrandSettingsModel.team_id.is_(None))
                .limit(1)
            )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        row = _build_default_row(team_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        logger.info("Brand settings: created default row (id=%s, team_id=%s)", row.id, team_id)
        return row


async def update_brand_settings(team_id: str | None = None, **kwargs) -> BrandSettingsModel:
    """Update brand settings for a team and refresh the cache."""
    async with AsyncSessionLocal() as session:
        if team_id:
            result = await session.execute(
                select(BrandSettingsModel).where(BrandSettingsModel.team_id == team_id)
            )
        else:
            result = await session.execute(
                select(BrandSettingsModel)
                .where(BrandSettingsModel.team_id.is_(None))
                .limit(1)
            )
        row = result.scalar_one_or_none()
        if row is None:
            row = await get_brand_settings(team_id)
            async with AsyncSessionLocal() as s2:
                if team_id:
                    result = await s2.execute(
                        select(BrandSettingsModel).where(BrandSettingsModel.team_id == team_id)
                    )
                else:
                    result = await s2.execute(
                        select(BrandSettingsModel)
                        .where(BrandSettingsModel.team_id.is_(None))
                        .limit(1)
                    )
                row = result.scalar_one_or_none()
        for key, value in kwargs.items():
            if hasattr(row, key):
                setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
        await _refresh_cache(team_id)
        return row


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


async def preload_brand_settings() -> None:
    """Call once at startup to populate the sync cache (global/default settings)."""
    _cache[None] = await get_brand_settings(team_id=None)
    logger.info("Brand settings cache preloaded")


async def _refresh_cache(team_id: str | None = None) -> None:
    _cache[team_id] = await get_brand_settings(team_id)


def get_brand_settings_cached(team_id: str | None = None) -> BrandSettingsModel:
    """Sync getter for agents running in ``run_in_executor``.

    Raises ``BrandSettingsNotLoaded`` if ``preload_brand_settings()`` was not
    called (typically during bot startup).
    Falls back to global settings if team-specific settings not cached.
    """
    if team_id in _cache:
        return _cache[team_id]
    if None in _cache:
        return _cache[None]
    raise BrandSettingsNotLoaded(
        "Brand settings not loaded. Call preload_brand_settings() at startup."
    )
