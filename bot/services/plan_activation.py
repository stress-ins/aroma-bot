"""Plan activation service -- resolves schedule slots and creates drafts."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from bot.services.plans_store import get_plan, update_plan_status
from bot.services.drafts_store import save_draft, update_draft

logger = logging.getLogger(__name__)

_DAY_MAP: dict[str, int] = {
    "Пн": 0, "Вт": 1, "Ср": 2, "Чт": 3,
    "Пт": 4, "Сб": 5, "Вс": 6,
}

_PLATFORM_TIME_UTC: dict[str, tuple[int, int]] = {
    "threads": (7, 0),
    "instagram": (9, 0),
    "telegram": (6, 0),
}


def _resolve_scheduled_at(day_label: str, platform: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    target_weekday = _DAY_MAP.get(day_label)
    if target_weekday is None:
        target_weekday = (now.weekday() + 1) % 7

    days_ahead = (target_weekday - now.weekday()) % 7
    if days_ahead == 0:
        h, m = _PLATFORM_TIME_UTC.get(platform.lower(), (7, 0))
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= now:
            days_ahead = 7

    target_date = (now + timedelta(days=days_ahead)).date()
    h, m = _PLATFORM_TIME_UTC.get(platform.lower(), (7, 0))
    return datetime(target_date.year, target_date.month, target_date.day, h, m, tzinfo=timezone.utc)


def _entry_platform(entry: dict) -> str:
    raw = str(entry.get("platform", "")).strip().lower()
    if "threads" in raw:
        return "threads"
    if "instagram" in raw or "reels" in raw or "carousel" in raw:
        return "instagram"
    if "telegram" in raw:
        return "telegram"
    return "threads"


def _entry_kind(entry: dict) -> str:
    fmt = str(entry.get("format_label", "")).strip().lower()
    platform = str(entry.get("platform", "")).strip().lower()
    if "reels" in fmt or "рилс" in fmt:
        return "reels"
    if "карус" in fmt or "carousel" in fmt:
        return "carousel"
    if "threads" in platform:
        return "threads"
    if "telegram" in platform:
        return "telegram"
    return "instagram"


async def _create_draft_from_entry(
    entry: dict, plan_id: str, now: datetime | None,
) -> dict:
    """Create a single scheduled draft from a plan entry."""
    topic = str(entry.get("topic", "")).strip()
    if not topic:
        return {}

    platform = _entry_platform(entry)
    kind = _entry_kind(entry)
    day_label = str(entry.get("day_label", "")).strip()
    scheduled_at = _resolve_scheduled_at(day_label, platform, now=now)
    platform_display = {"instagram": "Instagram", "threads": "Threads", "telegram": "Telegram"}.get(
        platform, platform.capitalize(),
    )

    draft = await save_draft(
        kind=kind, topic=topic, source="/plan-activate",
        payload={"angle": entry.get("angle", ""), "goal": entry.get("goal", ""), "plan_id": plan_id},
    )

    await update_draft(
        draft.draft_id, status="scheduled",
        scheduled_at=scheduled_at, publish_platforms=[platform_display],
    )

    return {
        "draft_id": draft.draft_id, "topic": topic,
        "scheduled_at": scheduled_at.isoformat(),
    }


async def activate_plan(plan_id: str, now: datetime | None = None) -> dict:
    plan = await get_plan(plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")

    await update_plan_status(plan_id, "activating")

    try:
        tasks = [
            _create_draft_from_entry(entry, plan_id, now)
            for entry in plan.entries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        created_drafts: list[dict] = []
        failures = 0
        for r in results:
            if isinstance(r, Exception):
                logger.error("Plan entry activation failed: %s", r)
                failures += 1
            elif r:  # skip empty dicts from entries without topic
                created_drafts.append(r)

        if failures and not created_drafts:
            await update_plan_status(plan_id, "failed")
            raise RuntimeError(f"All {failures} plan entries failed to activate")

        await update_plan_status(plan_id, "active")
    except Exception:
        logger.exception("Plan activation failed for %s", plan_id)
        await update_plan_status(plan_id, "failed")
        raise

    return {"plan_id": plan_id, "activated_count": len(created_drafts), "drafts": created_drafts}
