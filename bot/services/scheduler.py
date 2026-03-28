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


def _split_message(text: str, max_len: int = 4096) -> list[str]:
    """Split a message into chunks of at most max_len characters, breaking on newlines."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > max_len and current:
            chunks.append("".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


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

    # Persist digest to DB so it survives restarts
    try:
        from bot.services.digest_store import save_digest
        await save_digest(ru_report, en_report)
    except Exception as exc:
        logger.error("Failed to persist digest to DB: %s", exc)

    for report in (ru_report, en_report):
        for chunk in _split_message(report):
            try:
                await app.bot.send_message(
                    chat_id=settings.report_target_chat_id,
                    text=chunk,
                    parse_mode="MarkdownV2",
                    disable_web_page_preview=True,
                )
            except Exception:
                plain = chunk.replace("\\", "")
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
    """Find scheduled drafts due for publishing and publish them.

    For threads_series drafts: publishes individual slots at their scheduled_time.
    For other drafts: publishes the whole draft at scheduled_at.
    """
    from bot.services.drafts_store import list_scheduled_drafts_due
    from bot.services.publisher import publish

    drafts = await list_scheduled_drafts_due()
    now = datetime.now(timezone.utc)

    for draft in drafts:
        try:
            if draft.kind == "threads_series":
                await _publish_series_slots(draft, now)
            else:
                platforms = draft.publish_platforms or ["threads"]
                await publish(draft.draft_id, platforms)
                logger.info("Scheduled post published: %s", draft.draft_id)
        except Exception as exc:
            logger.error(
                "Failed to publish scheduled draft %s: %s", draft.draft_id, exc
            )


async def _publish_series_slots(draft, now: datetime) -> None:
    """Publish due slots of a threads_series one by one."""
    from bot.services.publisher import publish_threads_series_slot

    posts = (draft.payload or {}).get("threads_posts", [])
    scheduled_at = draft.scheduled_at
    if isinstance(scheduled_at, str):
        base_date = datetime.fromisoformat(scheduled_at).date()
    else:
        base_date = scheduled_at.date() if scheduled_at else now.date()

    for post in posts:
        if post.get("status") != "scheduled":
            continue

        time_str = post.get("scheduled_time", "09:00")
        try:
            h, m = map(int, time_str.split(":"))
        except ValueError:
            logger.warning("_publish_series_slots: map failed", exc_info=True)
            continue

        slot_time = datetime(
            base_date.year, base_date.month, base_date.day,
            h, m, tzinfo=timezone.utc,
        )
        if slot_time <= now:
            try:
                await publish_threads_series_slot(draft.draft_id, post["slot"])
                logger.info(
                    "Published series slot %s for draft %s",
                    post["slot"], draft.draft_id,
                )
            except Exception as exc:
                logger.error(
                    "Failed to publish series slot %s for draft %s: %s",
                    post["slot"], draft.draft_id, exc,
                )
                try:
                    from bot.handlers.monitor import notify_owner
                    await notify_owner(
                        f"⚠️ Scheduled publish failed for {draft.draft_id}:\n"
                        f"  {post['slot']}: {exc}"
                    )
                except Exception:
                    logger.warning("scheduler: suppressed exception", exc_info=True)
                    pass


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

# Social trends collection + pipeline: every 6 hours
_SOCIAL_TRENDS_HOURS = {3, 9, 15, 21}

# Pipeline delay between collect and enrich (seconds)
_PIPELINE_ENRICH_DELAY = 300  # 5 minutes

# Comments polling: every 3 hours at :30 (offset from social trends at :00)
_COMMENTS_POLL_HOURS = {0, 3, 6, 9, 12, 15, 18, 21}
_COMMENTS_POLL_MINUTE = 30


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


async def _run_trend_enrichment() -> None:
    from analytics.signal_enricher import enrich_signals

    count = await enrich_signals()
    if count:
        logger.info("Enriched %d trend signals", count)


async def _fetch_post_metrics() -> None:
    from bot.services.metrics_fetcher import fetch_all_pending_metrics

    count = await fetch_all_pending_metrics()
    if count:
        logger.info("Fetched metrics for %d published drafts", count)


async def _collect_social_trends() -> None:
    """Iterate over all teams with configured social accounts and collect posts."""
    from bot.services.social_trends_store import list_teams_with_social_accounts
    from bot.services.mentions_store import get_token_for_team
    from bot.services.brand_settings_store import get_brand_settings
    from analytics.instagram_trends import InstagramTrendsCollector
    from analytics.threads_trends_api import ThreadsTrendsCollector

    teams = await list_teams_with_social_accounts()
    if not teams:
        return

    logger.info("Social trends: collecting for %d team(s)", len(teams))

    for team in teams:
        team_id = team["team_id"]
        try:
            # Instagram collection
            if team["has_ig"]:
                ig_token = await get_token_for_team("instagram", team_id)
                ig_uid = await get_token_for_team("instagram_user_id", team_id)
                ig_username_rec = await get_token_for_team("instagram_username", team_id)
                if ig_token and ig_uid:
                    settings = await get_brand_settings(team_id)
                    own_ig = ig_username_rec.access_token if ig_username_rec else ""
                    collector = InstagramTrendsCollector(
                        team_id, ig_token.access_token, ig_uid.access_token,
                        own_username=own_ig,
                    )
                    count = await collector.collect_from_accounts(
                        settings.instagram_accounts or []
                    )
                    logger.info("Social trends: IG collected %d posts (team=%s)", count, team_id)

            # Threads collection
            if team["has_threads"]:
                th_token = await get_token_for_team("threads", team_id)
                th_uid = await get_token_for_team("threads_user_id", team_id)
                th_username_rec = await get_token_for_team("threads_username", team_id)
                if th_token and th_uid:
                    settings = await get_brand_settings(team_id)
                    own_th = th_username_rec.access_token if th_username_rec else ""
                    collector = ThreadsTrendsCollector(
                        team_id, th_token.access_token, th_uid.access_token
                    )
                    count = await collector.collect_from_accounts(
                        settings.threads_accounts or [], own_username=own_th,
                    )
                    logger.info("Social trends: Threads collected %d posts (team=%s)", count, team_id)
                    # Keyword search — find posts from other users
                    tracked_kw = list(settings.tracked_hashtags or [])
                    if tracked_kw:
                        kw_count = await collector.collect_from_keyword_search(tracked_kw)
                        if kw_count:
                            logger.info("Social trends: Threads keyword search %d posts (team=%s)", kw_count, team_id)
                    await collector.collect_own_insights()

        except Exception as exc:
            logger.error("Social trends failed for team %s: %s", team_id, exc)
        await asyncio.sleep(2)  # pause between teams


async def _run_trends_pipeline() -> None:
    """Unified pipeline: collect social trends -> enrich -> generate cards.

    Stages:
    1. Collect social trends from all teams
    2. Wait 5 minutes for data to settle
    3. Enrich new signals (velocity, lifecycle, sentiment)
    4. If any signals were enriched, generate trend cards

    Errors at any stage are logged but do not block subsequent runs.
    """
    from analytics.signal_enricher import enrich_signals
    from bot.agents.trend_card_generator import generate_and_save_cards

    # Stage 1: Collect
    try:
        await _collect_social_trends()
        logger.info("Trends pipeline: collected")
    except Exception as exc:
        logger.error("Trends pipeline: collect failed: %s", exc)

    # Stage 2: Delay before enrichment
    logger.info("Trends pipeline: waiting %d seconds before enrichment", _PIPELINE_ENRICH_DELAY)
    await asyncio.sleep(_PIPELINE_ENRICH_DELAY)

    # Stage 3: Enrich
    enriched = 0
    try:
        enriched = await enrich_signals()
        logger.info("Trends pipeline: enriched %d signals", enriched)
    except Exception as exc:
        logger.error("Trends pipeline: enrichment failed: %s", exc)

    # Stage 4: Generate cards (only if enrichment produced results)
    cards_count = 0
    if enriched > 0:
        try:
            cards = await generate_and_save_cards()
            cards_count = len(cards)
            logger.info("Trends pipeline: generated %d cards", cards_count)
        except Exception as exc:
            logger.error("Trends pipeline: card generation failed: %s", exc)

    logger.info(
        "Trends pipeline: collected -> enriched %d -> generated %d cards",
        enriched, cards_count,
    )


async def run_loop(app: Application) -> None:
    """Main scheduler loop — runs forever.

    Every 60 seconds:
    - Checks if daily digest should fire
    - Checks if daily/weekly cost report should fire
    - Publishes any scheduled posts that are due
    - Fetches post engagement metrics every 6 hours
    - Collects social trends every 6 hours
    """
    last_digest_date: date | None = None
    last_cost_report_date: date | None = None
    last_daily_oil_date: date | None = None
    last_metrics_fetch_hour: int | None = None
    last_thread_monitor_hour: int | None = None
    last_social_trends_hour: int | None = None
    last_status_check_minute: int | None = None
    last_mentions_poll_minute: int | None = None
    last_token_check_date: date | None = None
    last_comments_poll_hour: int | None = None
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

            # Social trends pipeline every 6 hours (collect -> enrich -> cards)
            if (
                now.hour in _SOCIAL_TRENDS_HOURS
                and now.minute == 0
                and last_social_trends_hour != now.hour
            ):
                last_social_trends_hour = now.hour
                try:
                    await _run_trends_pipeline()
                except Exception as exc:
                    logger.error("Trends pipeline failed: %s", exc)

            # Comments polling every 3 hours at :30
            if (
                now.hour in _COMMENTS_POLL_HOURS
                and now.minute == _COMMENTS_POLL_MINUTE
                and last_comments_poll_hour != now.hour
            ):
                last_comments_poll_hour = now.hour
                try:
                    from bot.services.comments_poller import poll_published_comments
                    total_polled, newly_saved = await poll_published_comments()
                    if newly_saved:
                        logger.info(
                            "Comments poll: %d new comments from %d polled",
                            newly_saved, total_polled,
                        )
                except Exception as exc:
                    logger.error("Comments poll failed: %s", exc)

            # Mentions poll every 5 minutes
            if (
                now.minute % 5 == 0
                and last_mentions_poll_minute != now.minute
            ):
                last_mentions_poll_minute = now.minute
                try:
                    from bot.services.mentions_poller import poll_all_teams
                    results = await poll_all_teams()
                    total_saved = sum(s for _, s in results.values())
                    if total_saved:
                        logger.info("Mentions poll: saved %d new", total_saved)
                except Exception as exc:
                    logger.error("Mentions poll failed: %s", exc)

            # Daily token expiry check at 04:00 UTC
            if (
                now.hour == 4
                and now.minute == 0
                and last_token_check_date != now.date()
            ):
                last_token_check_date = now.date()
                try:
                    from bot.services.mentions_poller import check_expiring_tokens
                    await check_expiring_tokens()
                except Exception as exc:
                    logger.error("Token expiry check failed: %s", exc)

            # Status monitor every 5 minutes
            if (
                now.minute % 5 == 0
                and last_status_check_minute != now.minute
            ):
                last_status_check_minute = now.minute
                try:
                    from bot.services.status_monitor import check_status_feeds
                    await check_status_feeds()
                except Exception as exc:
                    logger.error("Status monitor failed: %s", exc)

            # Scheduled posts
            try:
                await _check_scheduled_posts(app)
            except Exception as exc:
                logger.error("Scheduled post check failed: %s", exc)

        except Exception as exc:
            logger.error("Scheduler loop error: %s", exc)
