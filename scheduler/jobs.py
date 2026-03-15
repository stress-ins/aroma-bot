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


async def _check_scheduled_posts(app: Application) -> None:
    """Every 5 min: find approved drafts with scheduled_at <= now(), publish them."""
    from bot.services.drafts_store import list_scheduled_drafts_due, update_draft
    from bot.services.publisher import publish

    try:
        drafts = await list_scheduled_drafts_due()
        for draft in drafts:
            try:
                platforms = draft.publish_platforms or ["threads"]
                await publish(draft.draft_id, platforms)
                await update_draft(draft.draft_id, status="published")
                logger.info("Scheduled post published: %s", draft.draft_id)
            except Exception as exc:
                logger.error("Failed to publish scheduled draft %s: %s", draft.draft_id, exc)
    except Exception as exc:
        logger.error("_check_scheduled_posts error: %s", exc)


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    # NOTE: daily_digest is now triggered by n8n (workflow 01_trends_schedule.json).
    # APScheduler job removed — n8n POSTs to /api/trends/trigger at 06:00 UTC.
    scheduler.add_job(
        _check_scheduled_posts,
        trigger="interval",
        minutes=5,
        args=[app],
        id="check_scheduled_posts",
        name="Check & publish scheduled posts",
        replace_existing=True,
    )
    logger.info("Scheduled post checker running every 5 minutes")
    logger.info("Daily digest scheduling delegated to n8n (POST /api/trends/trigger)")
    return scheduler
