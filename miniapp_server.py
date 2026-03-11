from __future__ import annotations

import asyncio
import hashlib
import hmac
import urllib.parse
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bot.agents import generate_content_draft
from bot.agents.planner import generate_plan_sync
from bot.agents.reels_agent import generate_reels_director_sync, generate_reels_scenario_sync
from bot.handlers.planner import _parse_plan_entries
from bot.handlers.threads import _format_trends
from bot.services.miniapp_content_review import (
    polish_content_review_draft,
    update_content_review_draft,
)
from bot.services.miniapp_plan_actions import normalize_plan_format, normalize_plan_goal
from bot.services.reels_assets import ASSETS_DIR, regenerate_reels_frame_asset
from bot.services.drafts_store import get_draft, list_recent_drafts, update_draft
from bot.services.drafts_store import save_draft
from bot.services.miniapp_generator import (
    build_content_payload,
    build_reels_payload,
    is_valid_content_format,
    is_valid_content_goal,
)
from bot.services.miniapp_inbox import list_inbox_items
from bot.services.miniapp_keywords import add_keyword, delete_keyword, field_labels, serialize_topics
from bot.services.miniapp_plans import serialize_plan
from bot.services.miniapp_presenter import filter_drafts, serialize_draft
from bot.services.miniapp_reels import (
    build_reels_export_payload,
    list_reels_drafts,
    serialize_reels_draft,
    update_reels_frame_note,
    update_reels_frame_prompt,
)
from bot.services.plans_store import get_plan, list_recent_plans, save_plan
from config import settings


BASE_DIR = Path(__file__).parent
MINIAPP_DIR = BASE_DIR / "miniapp"
STATIC_DIR = MINIAPP_DIR / "static"


def _verify_init_data(init_data: str) -> bool:
    """Validate Telegram WebApp initData using HMAC-SHA256."""
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop("hash", "")
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_hash, received_hash)
    except Exception:
        return False


def _require_auth(x_telegram_init_data: str | None = Header(default=None)) -> None:
    """FastAPI dependency: validate Telegram initData header on mutating endpoints."""
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")


app = FastAPI()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="miniapp-static")
app.mount("/generated/reels_assets", StaticFiles(directory=ASSETS_DIR), name="reels-generated-assets")


class DraftStatusPayload(BaseModel):
    status: str


class DraftFeedbackPayload(BaseModel):
    feedback: str


class DraftContentPayload(BaseModel):
    topic: str = Field(default="")
    angle: str = Field(default="")
    hook: str = Field(default="")
    caption: str = Field(default="")
    cta: str = Field(default="")
    hashtags: str = Field(default="")
    visual_prompt: str = Field(default="")


class KeywordPayload(BaseModel):
    topic_idx: int
    field: str
    word: str


class ReelsFrameNotePayload(BaseModel):
    note: str = Field(default="")


class ReelsFramePromptPayload(BaseModel):
    prompt: str = Field(default="")


class CreateContentPayload(BaseModel):
    topic: str = Field(default="")
    goal_key: str = Field(default="")
    format_key: str = Field(default="")


class CreateReelsPayload(BaseModel):
    topic: str = Field(default="")


class PlanGeneratePayload(BaseModel):
    entry_index: int


@app.get("/")
async def index():
    return FileResponse(MINIAPP_DIR / "index.html")


@app.get("/healthz")
async def healthz():
    return JSONResponse({"ok": True, "service": "miniapp"})


@app.get("/api/drafts")
async def drafts(
    limit: int = Query(default=50, ge=1, le=200),
    kind: str = "",
    status: str = "",
    feedback: str = "",
    query: str = "",
):
    records = list_recent_drafts(limit=200)
    filtered = filter_drafts(
        records,
        kind=kind,
        status=status,
        feedback=feedback,
        query=query,
    )
    return {
        "items": [serialize_draft(record) for record in filtered[:limit]],
        "total": len(filtered),
    }


@app.get("/api/drafts/{draft_id}")
async def draft_detail(draft_id: str):
    draft = get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return serialize_draft(draft)


@app.post("/api/drafts/{draft_id}/status")
async def update_status(draft_id: str, payload: DraftStatusPayload, _: None = Depends(_require_auth)):
    status = payload.status.strip().lower()
    if status not in {"draft", "in_review", "approved", "published"}:
        raise HTTPException(status_code=400, detail="invalid_status")
    draft = update_draft(draft_id, status=status)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return serialize_draft(draft)


@app.post("/api/drafts/{draft_id}/feedback")
async def update_feedback(draft_id: str, payload: DraftFeedbackPayload, _: None = Depends(_require_auth)):
    feedback = payload.feedback.strip().lower()
    if feedback not in {"", "worked", "missed"}:
        raise HTTPException(status_code=400, detail="invalid_feedback")
    draft = update_draft(draft_id, feedback=feedback)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return serialize_draft(draft)


@app.post("/api/drafts/{draft_id}/content")
async def update_content(draft_id: str, payload: DraftContentPayload, _: None = Depends(_require_auth)):
    updated = update_content_review_draft(
        draft_id,
        topic=payload.topic,
        angle=payload.angle,
        hook=payload.hook,
        caption=payload.caption,
        cta=payload.cta,
        hashtags=payload.hashtags,
        visual_prompt=payload.visual_prompt,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="content_draft_not_found")
    draft = get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return serialize_draft(draft)


@app.post("/api/drafts/{draft_id}/content/polish")
async def polish_content(draft_id: str, _: None = Depends(_require_auth)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")
    updated = polish_content_review_draft(draft_id)
    if not updated:
        raise HTTPException(status_code=404, detail="content_draft_not_found")
    draft = get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return serialize_draft(draft)


@app.get("/api/status")
async def status():
    sources = [
        "google_trends_ru",
        "google_trends_en",
        "youtube",
        "reddit",
        "telegram_channels",
        "twitter",
        "instagram",
        "vk",
        "wordstat",
        "tiktok",
        "tiktok_ru",
        "threads",
        "ai_recommendations",
    ]
    return {
        "items": [{"source": source, "enabled": settings.is_source_enabled(source)} for source in sources],
        "digest_time": settings.daily_digest_time,
        "timezone": settings.timezone,
        "mini_app_url": settings.mini_app_url,
    }


@app.post("/api/generate/content")
async def generate_content(payload: CreateContentPayload, _: None = Depends(_require_auth)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")

    topic = payload.topic.strip()
    goal_key = payload.goal_key.strip().lower()
    format_key = payload.format_key.strip().lower()

    if not topic:
        raise HTTPException(status_code=400, detail="empty_topic")
    if not is_valid_content_goal(goal_key):
        raise HTTPException(status_code=400, detail="invalid_goal")
    if not is_valid_content_format(format_key):
        raise HTTPException(status_code=400, detail="invalid_format")

    draft = await generate_content_draft(topic, goal_key, format_key)
    saved = save_draft(
        kind=format_key,
        topic=topic,
        source="/miniapp",
        payload=build_content_payload(draft, goal_key=goal_key, format_key=format_key),
    )
    return serialize_draft(saved)


@app.post("/api/generate/reels")
async def generate_reels(payload: CreateReelsPayload, _: None = Depends(_require_auth)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")

    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="empty_topic")

    loop = asyncio.get_running_loop()
    scenario = await loop.run_in_executor(None, generate_reels_scenario_sync, topic)
    frames = await loop.run_in_executor(None, generate_reels_director_sync, topic, scenario)
    saved = save_draft(
        kind="reels",
        topic=topic,
        source="/miniapp",
        payload=build_reels_payload(topic, scenario, frames),
    )
    draft = serialize_reels_draft(saved.draft_id)
    if not draft:
        raise HTTPException(status_code=500, detail="reels_not_saved")
    return draft


@app.post("/api/generate/plan")
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
    record = save_plan(
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
    return serialize_plan(record)


@app.get("/api/inbox")
async def inbox(limit: int = Query(default=50, ge=1, le=200), kind: str = "", _: None = Depends(_require_auth)):
    items = list_inbox_items(limit=limit, kind_filter=kind)
    return {
        "items": items,
        "total": len(items),
        "kind": kind.strip().lower() or "all",
    }


@app.get("/api/plans")
async def plans(limit: int = Query(default=20, ge=1, le=100)):
    records = list_recent_plans(limit=limit)
    return {
        "items": [serialize_plan(record) for record in records],
        "total": len(records),
    }


@app.get("/api/plans/{plan_id}")
async def plan_detail(plan_id: str):
    record = get_plan(plan_id)
    if not record:
        raise HTTPException(status_code=404, detail="plan_not_found")
    return serialize_plan(record)


@app.post("/api/plans/{plan_id}/generate")
async def plan_generate(plan_id: str, payload: PlanGeneratePayload, _: None = Depends(_require_auth)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")

    record = get_plan(plan_id)
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
        scenario = await loop.run_in_executor(None, generate_reels_scenario_sync, topic)
        frames = await loop.run_in_executor(None, generate_reels_director_sync, topic, scenario)
        saved = save_draft(
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
        draft = serialize_draft(saved)
        return {"kind": "draft", "draft": draft}

    goal_key = normalize_plan_goal(str(entry.get("goal", "")))
    content_draft = await generate_content_draft(topic, goal_key, target)
    saved = save_draft(
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
    draft = serialize_draft(saved)
    return {"kind": "draft", "draft": draft}


@app.get("/api/reels")
async def reels(limit: int = Query(default=30, ge=1, le=100)):
    items = list_reels_drafts(limit=limit)
    return {
        "items": items,
        "total": len(items),
    }


@app.get("/api/reels/{draft_id}")
async def reels_detail(draft_id: str):
    draft = serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@app.get("/api/reels/{draft_id}/export")
async def reels_export(draft_id: str, _: None = Depends(_require_auth)):
    payload = build_reels_export_payload(draft_id)
    if not payload:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return payload


@app.post("/api/reels/{draft_id}/frames/{frame_index}/note")
async def reels_frame_note(
    draft_id: str,
    frame_index: int,
    payload: ReelsFrameNotePayload,
    _: None = Depends(_require_auth),
):
    draft = update_reels_frame_note(draft_id, frame_index, payload.note)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_frame_not_found")
    return draft


@app.post("/api/reels/{draft_id}/frames/{frame_index}/prompt")
async def reels_frame_prompt(
    draft_id: str,
    frame_index: int,
    payload: ReelsFramePromptPayload,
    _: None = Depends(_require_auth),
):
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="empty_prompt")
    draft = update_reels_frame_prompt(draft_id, frame_index, prompt)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_frame_not_found")
    return draft


@app.post("/api/reels/{draft_id}/frames/{frame_index}/regenerate")
async def reels_frame_regenerate(
    draft_id: str,
    frame_index: int,
    _: None = Depends(_require_auth),
):
    regen_payload = regenerate_reels_frame_asset(draft_id, frame_index)
    if not regen_payload:
        raise HTTPException(status_code=404, detail="reels_frame_regenerate_failed")
    draft = serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@app.get("/api/keywords")
async def keywords():
    return {
        "items": serialize_topics(),
        "field_labels": field_labels(),
    }


@app.post("/api/keywords/add")
async def keyword_add(payload: KeywordPayload, _: None = Depends(_require_auth)):
    word = payload.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="empty_word")
    add_keyword(payload.topic_idx, payload.field, word)
    return {"ok": True, "items": serialize_topics(), "field_labels": field_labels()}


@app.post("/api/keywords/remove")
async def keyword_remove(payload: KeywordPayload, _: None = Depends(_require_auth)):
    word = payload.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="empty_word")
    delete_keyword(payload.topic_idx, payload.field, word)
    return {"ok": True, "items": serialize_topics(), "field_labels": field_labels()}
