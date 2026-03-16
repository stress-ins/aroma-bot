"""Asyncio-based scheduler — replaces APScheduler.

Runs two tasks in a single loop:
1. Daily digest at configured time
2. Publish scheduled posts every 60 seconds
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date, timezone

from telegram.ext import Application

from config import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 60  # seconds


async def _send_daily_digest(app: Application) -> None:
    """Collect trends and send daily digest to the configured chat."""
    from analytics.aggregator import collect_all
    from formatters.report import build_report
    from cache.store import cache

    logger.info("Running daily digest job...")
    cached = cache.get("digest")
    if cached:
        ru_report, en_report = cached
        logger.info("Using cached report")
    else:
        results = await collect_all()
        ru_report = build_report(results, lang="ru")
        en_report = build_report(results, lang="en")
        cache.set("digest", (ru_report, en_report))

    for report in (ru_report, en_report):
        try:
            await app.bot.send_message(
                chat_id=settings.report_target_chat_id,
                text=report,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )
        except Exception:
            plain = report.replace("\\", "")
            try:
                await app.bot.send_message(
                    chat_id=settings.report_target_chat_id,
                    text=plain,
                    disable_web_page_preview=True,
                )
            except Exception as exc:
                logger.error("Failed to send digest: %s", exc)

    logger.info("Daily digest sent to %s", settings.report_target_chat_id)


async def _check_scheduled_posts(app: Application) -> None:
    """Find scheduled drafts due for publishing and publish them."""
    from bot.services.drafts_store import list_scheduled_drafts_due
    from bot.services.publisher import publish

    drafts = await list_scheduled_drafts_due()
    for draft in drafts:
        try:
            platforms = draft.publish_platforms or ["threads"]
            await publish(draft.draft_id, platforms)
            logger.info("Scheduled post published: %s", draft.draft_id)
        except Exception as exc:
            logger.error(
                "Failed to publish scheduled draft %s: %s", draft.draft_id, exc
            )


def _is_digest_time(now: datetime) -> bool:
    """Check if current time matches configured digest time (±1 min)."""
    return now.hour == settings.digest_hour and now.minute == settings.digest_minute


# Cost report: daily at 19:30 UTC, weekly (last 7 days) additionally on Fridays
_COST_REPORT_HOUR = 19
_COST_REPORT_MINUTE = 30


def _is_cost_report_time(now: datetime) -> bool:
    return now.hour == _COST_REPORT_HOUR and now.minute == _COST_REPORT_MINUTE


async def _send_daily_cost_report(app: Application) -> None:
    from bot.handlers.cost_report_sender import send_cost_report
    from bot.services.cost_stats_store import date_range_today, get_cost_stats

    logger.info("Sending daily cost report...")
    since, until = date_range_today()
    stats = await get_cost_stats(since, until)
    await send_cost_report(stats, period_label=f"за {since}")
    logger.info("Daily cost report sent.")


async def _send_weekly_cost_report(app: Application) -> None:
    from bot.handlers.cost_report_sender import send_cost_report
    from bot.services.cost_stats_store import date_range_last7, get_cost_stats

    logger.info("Sending weekly cost report...")
    since, until = date_range_last7()
    stats = await get_cost_stats(since, until)
    await send_cost_report(stats, period_label=f"за неделю ({since} — {until})")
    logger.info("Weekly cost report sent.")


# Post metrics polling: every 6 hours (at :00 of 0, 6, 12, 18 UTC)
_METRICS_POLL_HOURS = {0, 6, 12, 18}

# Thread monitor: every 2 hours
_THREAD_MONITOR_HOURS = {0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22}


# Daily oil: 06:00 UTC (09:00 MSK)
_DAILY_OIL_HOUR = 6
_DAILY_OIL_MINUTE = 0


def _is_daily_oil_time(now: datetime) -> bool:
    return now.hour == _DAILY_OIL_HOUR and now.minute == _DAILY_OIL_MINUTE


async def _run_daily_oil(app: Application) -> None:
    from bot.services.daily_oil import select_daily_oil, send_daily_oil_notifications

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info("Selecting daily oil for %s...", today)
    await select_daily_oil(today)
    await send_daily_oil_notifications(app)
    logger.info("Daily oil job complete for %s", today)


async def _fetch_post_metrics() -> None:
    from bot.services.metrics_fetcher import fetch_all_pending_metrics

    count = await fetch_all_pending_metrics()
    if count:
        logger.info("Fetched metrics for %d published drafts", count)


async def run_loop(app: Application) -> None:
    """Main scheduler loop — runs forever.

    Every 60 seconds:
    - Checks if daily digest should fire
    - Checks if daily/weekly cost report should fire
    - Publishes any scheduled posts that are due
    - Fetches post engagement metrics every 6 hours
    """
    last_digest_date: date | None = None
    last_cost_report_date: date | None = None
    last_daily_oil_date: date | None = None
    last_metrics_fetch_hour: int | None = None
    last_thread_monitor_hour: int | None = None
    logger.info(
        "Scheduler loop started (digest at %s %s, post check every %ds)",
        settings.daily_digest_time,
        settings.timezone,
        _POLL_INTERVAL,
    )

    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            now = datetime.now(timezone.utc)

            # Daily digest
            if _is_digest_time(now) and last_digest_date != now.date():
                last_digest_date = now.date()
                try:
                    await _send_daily_digest(app)
                except Exception as exc:
                    logger.error("Daily digest failed: %s", exc)

            # Daily cost report at 19:30 UTC
            if _is_cost_report_time(now) and last_cost_report_date != now.date():
                last_cost_report_date = now.date()
                try:
                    await _send_daily_cost_report(app)
                    # On Fridays, also send weekly report
                    if now.weekday() == 4:
                        await _send_weekly_cost_report(app)
                except Exception as exc:
                    logger.error("Cost report failed: %s", exc)

            # Daily oil at 06:00 UTC
            if _is_daily_oil_time(now) and last_daily_oil_date != now.date():
                last_daily_oil_date = now.date()
                try:
                    await _run_daily_oil(app)
                except Exception as exc:
                    logger.error("Daily oil job failed: %s", exc)

            # Post metrics polling every 6 hours
            if (
                now.hour in _METRICS_POLL_HOURS
                and now.minute == 0
                and last_metrics_fetch_hour != now.hour
            ):
                last_metrics_fetch_hour = now.hour
                try:
                    await _fetch_post_metrics()
                except Exception as exc:
                    logger.error("Metrics fetch failed: %s", exc)

            # Thread monitor every 2 hours
            if (
                now.hour in _THREAD_MONITOR_HOURS
                and now.minute == 0
                and last_thread_monitor_hour != now.hour
            ):
                last_thread_monitor_hour = now.hour
                try:
                    from bot.services.thread_monitor import run_thread_monitor
                    count = await run_thread_monitor()
                    if count:
                        logger.info("Thread monitor: %d new relevant threads", count)
                except Exception as exc:
                    logger.error("Thread monitor failed: %s", exc)

            # Scheduled posts
            try:
                await _check_scheduled_posts(app)
            except Exception as exc:
                logger.error("Scheduled post check failed: %s", exc)

        except Exception as exc:
            logger.error("Scheduler loop error: %s", exc)
