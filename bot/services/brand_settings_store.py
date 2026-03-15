"""Centralised brand-settings store (SQLite, single-row)."""

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
# ---------------------------------------------------------------------------

_cache: BrandSettingsModel | None = None


class BrandSettingsNotLoaded(RuntimeError):
    """Raised when get_brand_settings_cached() is called before preload."""


# ---------------------------------------------------------------------------
# Async API
# ---------------------------------------------------------------------------


async def get_brand_settings() -> BrandSettingsModel:
    """Return the single brand-settings row, creating a default if absent."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BrandSettingsModel).limit(1))
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        row = BrandSettingsModel(
            brand_voice=_DEFAULT_BRAND_VOICE,
            forbidden_phrases=list(_DEFAULT_FORBIDDEN_PHRASES),
            base_instructions="",
            target_platforms=list(_DEFAULT_TARGET_PLATFORMS),
            upload_post_user="",
            upload_post_api_key="",
            updated_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        logger.info("Brand settings: created default row (id=%s)", row.id)
        return row


async def update_brand_settings(**kwargs) -> BrandSettingsModel:
    """Update brand settings and refresh the cache."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BrandSettingsModel).limit(1))
        row = result.scalar_one_or_none()
        if row is None:
            row = await get_brand_settings()
            result = await session.execute(select(BrandSettingsModel).limit(1))
            row = result.scalar_one_or_none()
        for key, value in kwargs.items():
            if hasattr(row, key):
                setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
        await _refresh_cache()
        return row


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


async def preload_brand_settings() -> None:
    """Call once at startup to populate the sync cache."""
    global _cache
    _cache = await get_brand_settings()
    logger.info("Brand settings cache preloaded")


async def _refresh_cache() -> None:
    global _cache
    _cache = await get_brand_settings()


def get_brand_settings_cached() -> BrandSettingsModel:
    """Sync getter for agents running in ``run_in_executor``.

    Raises ``BrandSettingsNotLoaded`` if ``preload_brand_settings()`` was not
    called (typically during bot startup).
    """
    if _cache is None:
        raise BrandSettingsNotLoaded(
            "Brand settings not loaded. Call preload_brand_settings() at startup."
        )
    return _cache
