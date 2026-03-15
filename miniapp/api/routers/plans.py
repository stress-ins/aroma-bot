from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, and_, select

from bot.agents.planner import generate_plan_sync
from bot.agents.reels_agent import generate_reels_director_sync, generate_reels_scenario_sync
from bot.handlers.planner import _parse_plan_entries
from bot.handlers.threads import _format_trends
from bot.services.drafts_store import save_draft
from bot.services.miniapp_plan_actions import normalize_plan_format, normalize_plan_goal
from bot.services.miniapp_plans import serialize_plan
from bot.services.miniapp_presenter import serialize_draft
from bot.services.miniapp_inbox import list_inbox_items
from bot.services.miniapp_references import build_reference_context
from bot.agents import generate_content_draft
from bot.services.plans_store import get_plan, list_recent_plans, save_plan
from config import settings
from db.models import DraftModel
from db.session import AsyncSessionLocal
from ..auth import _require_auth
from ..models import PlanGeneratePayload


def _kind_to_platform(kind: str) -> str:
    mapping = {
        "threads": "Threads",
        "threads_series": "Threads",
        "instagram": "Instagram",
        "carousel": "Instagram",
        "reels": "Instagram",
        "telegram": "Telegram",
        "tiktok": "TikTok",
        "youtube": "YouTube",
    }
    return mapping.get(kind.lower(), kind.capitalize())

router = APIRouter()


@router.get("/api/inbox")
async def inbox(limit: int = Query(default=50, ge=1, le=200), kind: str = "", _: None = Depends(_require_auth)):
    items = await list_inbox_items(limit=limit, kind_filter=kind)
    return {"items": items, "total": len(items), "kind": kind.strip().lower() or "all"}


@router.get("/api/plans/feed")
async def plans_feed(
    status: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    _: None = Depends(_require_auth),
):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)

    async with AsyncSessionLocal() as session:
        query = select(DraftModel).filter(
            or_(
                DraftModel.status == "scheduled",
                and_(
                    DraftModel.status == "published",
                    or_(
                        DraftModel.published_at >= cutoff,
                        DraftModel.created_at >= cutoff,
                    ),
                ),
                and_(
                    DraftModel.error.isnot(None),
                    DraftModel.error != "",
                    DraftModel.created_at >= cutoff,
                ),
            )
        ).order_by(DraftModel.scheduled_at.asc())
        result = await session.execute(query)
        drafts = result.scalars().all()

    items: list[dict] = []
    all_dates: set[str] = set()

    for draft in drafts:
        payload: dict = draft.payload or {}
        platforms: list[str] = list(draft.publish_platforms or [])

        if draft.kind == "threads_series":
            posts = payload.get("threads_posts", [])
            base_date = draft.scheduled_at.date() if draft.scheduled_at else None

            for post in posts:
                slot = post.get("slot", "")
                slot_status = post.get("status", "draft")
                if slot_status not in ("scheduled", "published", "error"):
                    continue

                slot_scheduled_at: str | None = None
                if base_date and post.get("scheduled_time"):
                    try:
                        h, m = str(post["scheduled_time"]).split(":")
                        dt = datetime(
                            base_date.year, base_date.month, base_date.day,
                            int(h), int(m), tzinfo=timezone.utc,
                        )
                        slot_scheduled_at = dt.isoformat()
                    except Exception:
                        slot_scheduled_at = draft.scheduled_at.isoformat() if draft.scheduled_at else None
                elif draft.scheduled_at:
                    slot_scheduled_at = draft.scheduled_at.isoformat()

                if not slot_scheduled_at:
                    continue

                date_key = slot_scheduled_at[:10]
                all_dates.add(date_key)

                items.append({
                    "id": f"{draft.draft_id}_{slot}",
                    "draft_id": draft.draft_id,
                    "kind": draft.kind,
                    "slot": slot,
                    "title": draft.topic or "",
                    "preview": str(post.get("text", ""))[:100],
                    "platform": "Threads",
                    "platforms": ["Threads"],
                    "scheduled_at": slot_scheduled_at,
                    "status": slot_status,
                    "error_message": post.get("error_message") or None,
                    "published_at": None,
                })
        else:
            scheduled_at_str = draft.scheduled_at.isoformat() if draft.scheduled_at else None
            if not scheduled_at_str:
                continue

            if not platforms:
                platforms = [_kind_to_platform(draft.kind)]

            item_status = "published" if draft.status == "published" else "scheduled"
            if draft.error:
                item_status = "error"

            date_key = scheduled_at_str[:10]
            all_dates.add(date_key)

            preview = str(payload.get("caption") or payload.get("hook") or "")[:100]
            published_at_str = draft.published_at.isoformat() if draft.published_at else None

            for plat in platforms:
                items.append({
                    "id": f"{draft.draft_id}_{plat}",
                    "draft_id": draft.draft_id,
                    "kind": draft.kind,
                    "slot": None,
                    "title": draft.topic or "",
                    "preview": preview,
                    "platform": plat,
                    "platforms": platforms,
                    "scheduled_at": scheduled_at_str,
                    "status": item_status,
                    "error_message": draft.error or None,
                    "published_at": published_at_str,
                })

    # Apply optional filters
    if status and status != "all":
        items = [i for i in items if i["status"] == status]
    if platform and platform.lower() not in ("all", "все платформы"):
        items = [i for i in items if platform.lower() in [p.lower() for p in i["platforms"]]]

    items.sort(key=lambda x: x["scheduled_at"] or "")

    return {"items": items, "dates_with_content": sorted(all_dates)}


@router.get("/api/plans")
async def plans(limit: int = Query(default=20, ge=1, le=100), _: None = Depends(_require_auth)):
    records = await list_recent_plans(limit=limit)
    return {"items": [await serialize_plan(record) for record in records], "total": len(records)}


@router.get("/api/plans/{plan_id}")
async def plan_detail(plan_id: str, _: None = Depends(_require_auth)):
    record = await get_plan(plan_id)
    if not record:
        raise HTTPException(status_code=404, detail="plan_not_found")
    return await serialize_plan(record)


@router.post("/api/generate/plan")
async def generate_plan(_: None = Depends(_require_auth)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")

    from analytics.aggregator import collect_all
    from cache.store import cache

    results = cache.get("results")
    if not results:
        results = await collect_all()
        cache.set("results", results)

    trends_text = _format_trends(results)
    loop = asyncio.get_running_loop()
    raw_plan = await loop.run_in_executor(None, generate_plan_sync, trends_text)
    if not raw_plan:
        raise HTTPException(status_code=500, detail="plan_generation_failed")

    entries = _parse_plan_entries(raw_plan)
    record = await save_plan(
        raw_text=raw_plan,
        entries=[
            {
                "day_label": entry.day_label,
                "platform": entry.platform,
                "format_label": entry.format_label,
                "goal": entry.goal,
                "topic": entry.topic,
                "angle": entry.angle,
            }
            for entry in entries
        ],
    )
    return await serialize_plan(record)


@router.post("/api/plans/{plan_id}/generate")
async def plan_generate(plan_id: str, payload: PlanGeneratePayload, _: None = Depends(_require_auth)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")

    record = await get_plan(plan_id)
    if not record:
        raise HTTPException(status_code=404, detail="plan_not_found")
    if payload.entry_index < 0 or payload.entry_index >= len(record.entries):
        raise HTTPException(status_code=400, detail="invalid_entry_index")

    entry = dict(record.entries[payload.entry_index])
    topic = str(entry.get("topic", "")).strip()
    if not topic:
        raise HTTPException(status_code=400, detail="empty_topic")

    target = normalize_plan_format(entry)

    if target == "reels":
        loop = asyncio.get_running_loop()
        reference_context = await build_reference_context()
        scenario = await loop.run_in_executor(None, generate_reels_scenario_sync, topic, reference_context)
        frames = await loop.run_in_executor(None, generate_reels_director_sync, topic, scenario)
        saved = await save_draft(
            kind="reels",
            topic=topic,
            source="/plan",
            payload={
                "scenario": scenario,
                "storyboard": [
                    {
                        "timecode": frame.timecode,
                        "scene": frame.scene,
                        "angle": frame.angle,
                        "gemini_prompt": frame.gemini_prompt,
                    }
                    for frame in frames
                ],
                "images_ready": 0,
            },
        )
        draft = await serialize_draft(saved)
        return {"kind": "draft", "draft": draft}

    goal_key = normalize_plan_goal(str(entry.get("goal", "")))
    content_draft = await generate_content_draft(topic, goal_key, target)
    saved = await save_draft(
        kind=target,
        topic=topic,
        source="/plan",
        payload={
            "angle": content_draft.angle,
            "hook": content_draft.hook,
            "caption": content_draft.caption,
            "cta": content_draft.cta,
            "hashtags": content_draft.hashtags,
            "visual_prompt": content_draft.visual_prompt,
            "slides": list(content_draft.slides),
        },
    )
    draft = await serialize_draft(saved)
    return {"kind": "draft", "draft": draft}
