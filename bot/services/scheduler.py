"""Asyncio-based scheduler — declarative task registry.

All periodic tasks are declared as ScheduledTask instances in _build_task_registry().
The run_loop dispatches them based on the current UTC time.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Awaitable, Callable

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


# ---------------------------------------------------------------------------
# Task functions (business logic unchanged)
# ---------------------------------------------------------------------------

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
    """Find scheduled drafts due for publishing and publish them."""
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
                        f"\u26a0\ufe0f Scheduled publish failed for {draft.draft_id}:\n"
                        f"  {post['slot']}: {exc}"
                    )
                except Exception:
                    logger.warning("scheduler: suppressed exception", exc_info=True)


def _is_digest_time(now: datetime) -> bool:
    """Check if current time matches configured digest time."""
    return now.hour == settings.digest_hour and now.minute == settings.digest_minute


# Cost report: daily at 19:30 UTC
_COST_REPORT_HOUR = 19
_COST_REPORT_MINUTE = 30

# Constants kept at module level for backward compatibility with tests
_METRICS_POLL_HOURS = {0, 6, 12, 18}
_THREAD_MONITOR_HOURS = {0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22}
_SOCIAL_TRENDS_HOURS = {3, 9, 15, 21}
_PIPELINE_ENRICH_DELAY = 300  # 5 minutes
_COMMENTS_POLL_HOURS = {0, 3, 6, 9, 12, 15, 18, 21}
_COMMENTS_POLL_MINUTE = 30


async def _send_daily_cost_report(app: Application) -> None:
    from bot.handlers.cost_report_sender import send_cost_report
    from bot.services.cost_stats_store import date_range_today, get_cost_stats

    logger.info("Sending daily cost report...")
    since, until = date_range_today()
    stats = await get_cost_stats(since, until)
    await send_cost_report(stats, period_label=f"\u0437\u0430 {since}")
    logger.info("Daily cost report sent.")


async def _send_weekly_cost_report(app: Application) -> None:
    from bot.handlers.cost_report_sender import send_cost_report
    from bot.services.cost_stats_store import date_range_last7, get_cost_stats

    logger.info("Sending weekly cost report...")
    since, until = date_range_last7()
    stats = await get_cost_stats(since, until)
    await send_cost_report(stats, period_label=f"\u0437\u0430 \u043d\u0435\u0434\u0435\u043b\u044e ({since} \u2014 {until})")
    logger.info("Weekly cost report sent.")


async def _send_cost_reports(app: Application) -> None:
    """Send daily cost report; on Fridays also send weekly."""
    await _send_daily_cost_report(app)
    now = datetime.now(timezone.utc)
    if now.weekday() == 4:
        await _send_weekly_cost_report(app)


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


async def _run_thread_monitor() -> None:
    from bot.services.thread_monitor import run_thread_monitor

    count = await run_thread_monitor()
    if count:
        logger.info("Thread monitor: %d new relevant threads", count)


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
            if team["has_ig"]:
                ig_token = await get_token_for_team("instagram", team_id)
                ig_uid = await get_token_for_team("instagram_user_id", team_id)
                ig_username_rec = await get_token_for_team("instagram_username", team_id)
                if ig_token and ig_uid:
                    bs = await get_brand_settings(team_id)
                    own_ig = ig_username_rec.access_token if ig_username_rec else ""
                    collector = InstagramTrendsCollector(
                        team_id, ig_token.access_token, ig_uid.access_token,
                        own_username=own_ig,
                    )
                    count = await collector.collect_from_accounts(
                        bs.instagram_accounts or []
                    )
                    logger.info("Social trends: IG collected %d posts (team=%s)", count, team_id)

            if team["has_threads"]:
                th_token = await get_token_for_team("threads", team_id)
                th_uid = await get_token_for_team("threads_user_id", team_id)
                th_username_rec = await get_token_for_team("threads_username", team_id)
                if th_token and th_uid:
                    bs = await get_brand_settings(team_id)
                    own_th = th_username_rec.access_token if th_username_rec else ""
                    collector = ThreadsTrendsCollector(
                        team_id, th_token.access_token, th_uid.access_token
                    )
                    count = await collector.collect_from_accounts(
                        bs.threads_accounts or [], own_username=own_th,
                    )
                    logger.info("Social trends: Threads collected %d posts (team=%s)", count, team_id)
                    tracked_kw = list(bs.tracked_hashtags or [])
                    if tracked_kw:
                        kw_count = await collector.collect_from_keyword_search(tracked_kw)
                        if kw_count:
                            logger.info("Social trends: Threads keyword search %d posts (team=%s)", kw_count, team_id)
                    await collector.collect_own_insights()

        except Exception as exc:
            logger.error("Social trends failed for team %s: %s", team_id, exc)
        await asyncio.sleep(2)


async def _run_trends_pipeline() -> None:
    """Unified pipeline: collect social trends -> enrich -> generate cards."""
    from analytics.signal_enricher import enrich_signals
    from bot.agents.trend_card_generator import generate_and_save_cards

    try:
        await _collect_social_trends()
        logger.info("Trends pipeline: collected")
    except Exception as exc:
        logger.error("Trends pipeline: collect failed: %s", exc)

    logger.info("Trends pipeline: waiting %d seconds before enrichment", _PIPELINE_ENRICH_DELAY)
    await asyncio.sleep(_PIPELINE_ENRICH_DELAY)

    enriched = 0
    try:
        enriched = await enrich_signals()
        logger.info("Trends pipeline: enriched %d signals", enriched)
    except Exception as exc:
        logger.error("Trends pipeline: enrichment failed: %s", exc)

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


async def _poll_comments() -> None:
    from bot.services.comments_poller import poll_published_comments

    total_polled, newly_saved = await poll_published_comments()
    if newly_saved:
        logger.info("Comments poll: %d new comments from %d polled", newly_saved, total_polled)


async def _poll_mentions() -> None:
    from bot.services.mentions_poller import poll_all_teams

    results = await poll_all_teams()
    total_saved = sum(s for _, s in results.values())
    if total_saved:
        logger.info("Mentions poll: saved %d new", total_saved)


async def _check_expiring_tokens() -> None:
    from bot.services.mentions_poller import check_expiring_tokens
    await check_expiring_tokens()


async def _check_status_feeds() -> None:
    from bot.services.status_monitor import check_status_feeds
    await check_status_feeds()


# ---------------------------------------------------------------------------
# Declarative task registry
# ---------------------------------------------------------------------------

@dataclass
class ScheduledTask:
    """A declarative description of a periodic task.

    Scheduling modes (``check``):
      - ``"daily"``: once per calendar day when ``hours`` and ``minute`` match.
      - ``"hourly"``: once per matching hour at given ``minute``.
      - ``"every_Nm"``: every ``interval_minutes`` minutes.
      - ``"every_tick"``: every scheduler tick (60 s).

    ``needs_app``: if True the callable receives the Application instance.
    """

    name: str
    fn: Callable[..., Awaitable[None]]
    hours: set[int] | None = None
    minute: int = 0
    check: str = "hourly"
    interval_minutes: int = 0
    needs_app: bool = False

    _last_date: date | None = field(default=None, init=False, repr=False)
    _last_hour: int | None = field(default=None, init=False, repr=False)
    _last_minute: int | None = field(default=None, init=False, repr=False)

    def should_run(self, now: datetime) -> bool:
        """Return True if the task should fire at *now*, updating dedup state."""
        if self.check == "daily":
            if self._last_date == now.date():
                return False
            if self.hours is not None and now.hour not in self.hours:
                return False
            if now.minute != self.minute:
                return False
            self._last_date = now.date()
            return True

        if self.check == "hourly":
            if self._last_hour == now.hour:
                return False
            if self.hours is not None and now.hour not in self.hours:
                return False
            if now.minute != self.minute:
                return False
            self._last_hour = now.hour
            return True

        if self.check == "every_Nm":
            interval = self.interval_minutes
            if interval <= 0:
                return False
            if now.minute % interval != 0 or self._last_minute == now.minute:
                return False
            self._last_minute = now.minute
            return True

        if self.check == "every_tick":
            return True

        return False


def _build_task_registry() -> list[ScheduledTask]:
    """Build the registry of all scheduled tasks."""
    return [
        ScheduledTask(
            name="daily_digest",
            fn=_send_daily_digest,
            hours={settings.digest_hour},
            minute=settings.digest_minute,
            check="daily",
            needs_app=True,
        ),
        ScheduledTask(
            name="cost_report",
            fn=_send_cost_reports,
            hours={_COST_REPORT_HOUR},
            minute=_COST_REPORT_MINUTE,
            check="daily",
            needs_app=True,
        ),
        ScheduledTask(
            name="daily_oil",
            fn=_run_daily_oil,
            hours={6},
            minute=0,
            check="daily",
            needs_app=True,
        ),
        ScheduledTask(
            name="token_expiry_check",
            fn=_check_expiring_tokens,
            hours={4},
            minute=0,
            check="daily",
        ),
        ScheduledTask(
            name="post_metrics",
            fn=_fetch_post_metrics,
            hours=_METRICS_POLL_HOURS,
            minute=0,
            check="hourly",
        ),
        ScheduledTask(
            name="thread_monitor",
            fn=_run_thread_monitor,
            hours=_THREAD_MONITOR_HOURS,
            minute=0,
            check="hourly",
        ),
        ScheduledTask(
            name="social_trends_pipeline",
            fn=_run_trends_pipeline,
            hours=_SOCIAL_TRENDS_HOURS,
            minute=0,
            check="hourly",
        ),
        ScheduledTask(
            name="comments_poll",
            fn=_poll_comments,
            hours=_COMMENTS_POLL_HOURS,
            minute=_COMMENTS_POLL_MINUTE,
            check="hourly",
        ),
        ScheduledTask(
            name="mentions_poll",
            fn=_poll_mentions,
            check="every_Nm",
            interval_minutes=5,
        ),
        ScheduledTask(
            name="status_monitor",
            fn=_check_status_feeds,
            check="every_Nm",
            interval_minutes=5,
        ),
        ScheduledTask(
            name="scheduled_posts",
            fn=_check_scheduled_posts,
            check="every_tick",
            needs_app=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_loop(app: Application) -> None:
    """Main scheduler loop -- dispatches tasks from the registry every 60s."""
    registry = _build_task_registry()

    logger.info(
        "Scheduler loop started (%d tasks, digest at %s %s, post check every %ds)",
        len(registry),
        settings.daily_digest_time,
        settings.timezone,
        _POLL_INTERVAL,
    )

    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            now = datetime.now(timezone.utc)
            for task in registry:
                if task.should_run(now):
                    try:
                        if task.needs_app:
                            await task.fn(app)
                        else:
                            await task.fn()
                    except Exception as exc:
                        logger.error("%s failed: %s", task.name, exc)
        except Exception as exc:
            logger.error("Scheduler loop error: %s", exc)
