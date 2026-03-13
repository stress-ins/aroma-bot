from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

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
from ..auth import _require_auth
from ..models import PlanGeneratePayload

router = APIRouter()


@router.get("/api/inbox")
async def inbox(limit: int = Query(default=50, ge=1, le=200), kind: str = "", _: None = Depends(_require_auth)):
    items = await list_inbox_items(limit=limit, kind_filter=kind)
    return {"items": items, "total": len(items), "kind": kind.strip().lower() or "all"}


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
