from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from config import settings

logger = logging.getLogger(__name__)


async def _send_daily_digest(app: Application) -> None:
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


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        _send_daily_digest,
        trigger=CronTrigger(
            hour=settings.digest_hour,
            minute=settings.digest_minute,
            timezone=settings.timezone,
        ),
        args=[app],
        id="daily_digest",
        name="Daily Aroma Trends Digest",
        replace_existing=True,
    )
    logger.info(
        "Scheduled daily digest at %s (%s)",
        settings.daily_digest_time,
        settings.timezone,
    )
    return scheduler
