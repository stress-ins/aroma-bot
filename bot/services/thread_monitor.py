"""Monitor Threads for brand-relevant conversations.

Pipeline: collect -> dedup -> score -> persist -> notify.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from bot.services.threads_api import (
    ThreadsAPIError,
    ThreadsClient,
    WATCH_KEYWORDS,
    collect_inbox_candidates_sync,
)
from bot.services.tracked_threads_store import (
    is_already_tracked,
    save_tracked_thread,
    update_thread_scoring,
)

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _collect_deep_candidates_sync() -> list[dict]:
    """Collect mentions + replies + conversation threads. Sync, runs in executor."""
    try:
        me, candidates = collect_inbox_candidates_sync(limit_threads=8, limit_replies=15)
    except ThreadsAPIError as exc:
        logger.warning("collect_inbox_candidates_sync failed: %s", exc)
        return []

    username = str(me.get("username", "")).lower()
    results: list[dict] = []
    seen: set[str] = set()

    for c in candidates:
        if c.thread_id in seen:
            continue
        seen.add(c.thread_id)
        results.append({
            "thread_id": c.thread_id,
            "source": c.source,
            "author": c.author,
            "text": c.text,
            "permalink": c.permalink,
            "timestamp": c.timestamp,
            "root_text": c.root_text,
            "like_count": 0,
            "reply_count": 0,
        })

    # Deep mining: explore conversation threads around mentions
    try:
        client = ThreadsClient()
        for c in candidates[:5]:
            try:
                conversation = client.get_thread_conversation(c.thread_id, limit=8)
                for reply in conversation:
                    rid = str(reply.get("id", ""))
                    author = str(reply.get("username", "")).lower()
                    if not rid or rid in seen or author == username:
                        continue
                    seen.add(rid)
                    results.append({
                        "thread_id": rid,
                        "source": "conversation",
                        "author": str(reply.get("username", "")),
                        "text": str(reply.get("text", "")),
                        "permalink": str(reply.get("permalink", "")),
                        "timestamp": str(reply.get("timestamp", "")),
                        "root_text": c.text,
                        "like_count": 0,
                        "reply_count": 0,
                    })
            except ThreadsAPIError:
                logger.warning("thread_monitor: suppressed exception", exc_info=True)
                continue
    except ThreadsAPIError:
        logger.warning("thread_monitor: suppressed exception", exc_info=True)
        pass

    # Keyword search (placeholder)
    try:
        client = ThreadsClient()
        for keyword in WATCH_KEYWORDS:
            for post in client.search_threads(keyword, limit=10):
                tid = str(post.get("id", ""))
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                results.append({
                    "thread_id": tid,
                    "source": "search",
                    "author": str(post.get("username", "")),
                    "text": str(post.get("text", "")),
                    "permalink": str(post.get("permalink", "")),
                    "timestamp": str(post.get("timestamp", "")),
                    "root_text": "",
                    "keyword_matched": keyword,
                    "like_count": int(post.get("like_count", 0)),
                    "reply_count": int(post.get("repost_count", 0)),
                })
    except ThreadsAPIError:
        logger.warning("thread_monitor: suppressed exception", exc_info=True)
        pass

    return results


async def run_thread_monitor() -> int:
    """Collect -> dedup -> score -> persist -> notify. Returns count of new relevant."""
    from bot.agents.thread_scorer import score_threads_batch_sync
    from bot.handlers.monitor import notify_owner

    loop = asyncio.get_running_loop()

    raw_candidates = await loop.run_in_executor(_executor, _collect_deep_candidates_sync)
    if not raw_candidates:
        logger.info("Thread monitor: no candidates found")
        return 0

    new_candidates = []
    for c in raw_candidates:
        if not await is_already_tracked(c["thread_id"]):
            new_candidates.append(c)

    if not new_candidates:
        logger.info("Thread monitor: all candidates already tracked")
        return 0

    for c in new_candidates:
        await save_tracked_thread(
            c["thread_id"],
            platform="threads",
            source=c.get("source", "mention"),
            author_username=c.get("author", ""),
            text=c.get("text", ""),
            permalink=c.get("permalink", ""),
            root_text=c.get("root_text", ""),
            keyword_matched=c.get("keyword_matched", ""),
            like_count=c.get("like_count", 0),
            reply_count=c.get("reply_count", 0),
        )

    scored = await loop.run_in_executor(_executor, score_threads_batch_sync, new_candidates)

    relevant_count = 0
    high_relevance: list[dict] = []
    for item in scored:
        score = item.get("relevance_score", 0.0)
        await update_thread_scoring(
            item["thread_id"],
            relevance_score=score,
            suggested_action=item.get("suggested_action", "dismiss"),
            ai_summary=item.get("ai_summary", ""),
            content_angle=item.get("content_angle", ""),
            topic_tags=item.get("topic_tags", []),
        )
        if score >= 0.5:
            relevant_count += 1
        if score >= 0.7 and item.get("suggested_action") in ("reply", "create_content"):
            high_relevance.append(item)

    if high_relevance:
        lines = [f"🧵 Найдено {len(high_relevance)} релевантных веток в Threads:\n"]
        for item in high_relevance[:5]:
            lines.append(
                f"• @{item.get('author', '?')} ({item.get('relevance_score', 0):.0%})\n"
                f"  {item.get('ai_summary', '')}\n"
                f"  💡 {item.get('content_angle') or 'нет угла'}\n"
                f"  {item.get('permalink', '')}\n"
            )
        notify_owner("\n".join(lines))

    logger.info("Thread monitor: %d new, %d relevant", len(new_candidates), relevant_count)
    return relevant_count
