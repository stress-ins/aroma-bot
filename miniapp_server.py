from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot.services.drafts_store import get_draft, list_recent_drafts, update_draft
from bot.services.miniapp_keywords import add_keyword, delete_keyword, field_labels, serialize_topics
from bot.services.miniapp_plans import serialize_plan
from bot.services.miniapp_presenter import filter_drafts, serialize_draft
from bot.services.plans_store import get_plan, list_recent_plans
from config import settings


BASE_DIR = Path(__file__).parent
MINIAPP_DIR = BASE_DIR / "miniapp"
STATIC_DIR = MINIAPP_DIR / "static"

app = FastAPI()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="miniapp-static")


class DraftStatusPayload(BaseModel):
    status: str


class DraftFeedbackPayload(BaseModel):
    feedback: str


class KeywordPayload(BaseModel):
    topic_idx: int
    field: str
    word: str


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
async def update_status(draft_id: str, payload: DraftStatusPayload):
    status = payload.status.strip().lower()
    if status not in {"draft", "in_review", "approved", "published"}:
        raise HTTPException(status_code=400, detail="invalid_status")
    draft = update_draft(draft_id, status=status)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return serialize_draft(draft)


@app.post("/api/drafts/{draft_id}/feedback")
async def update_feedback(draft_id: str, payload: DraftFeedbackPayload):
    feedback = payload.feedback.strip().lower()
    if feedback not in {"", "worked", "missed"}:
        raise HTTPException(status_code=400, detail="invalid_feedback")
    draft = update_draft(draft_id, feedback=feedback)
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


@app.get("/api/keywords")
async def keywords():
    return {
        "items": serialize_topics(),
        "field_labels": field_labels(),
    }


@app.post("/api/keywords/add")
async def keyword_add(payload: KeywordPayload):
    word = payload.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="empty_word")
    add_keyword(payload.topic_idx, payload.field, word)
    return {"ok": True, "items": serialize_topics(), "field_labels": field_labels()}


@app.post("/api/keywords/remove")
async def keyword_remove(payload: KeywordPayload):
    word = payload.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="empty_word")
    delete_keyword(payload.topic_idx, payload.field, word)
    return {"ok": True, "items": serialize_topics(), "field_labels": field_labels()}
