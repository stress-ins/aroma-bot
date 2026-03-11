from __future__ import annotations

import hashlib
import hmac
import urllib.parse
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bot.services.drafts_store import get_draft, list_recent_drafts, update_draft
from bot.services.miniapp_inbox import list_inbox_items
from bot.services.miniapp_keywords import add_keyword, delete_keyword, field_labels, serialize_topics
from bot.services.miniapp_plans import serialize_plan
from bot.services.miniapp_presenter import filter_drafts, serialize_draft
from bot.services.miniapp_reels import (
    list_reels_drafts,
    serialize_reels_draft,
    update_reels_frame_note,
    update_reels_frame_prompt,
)
from bot.services.plans_store import get_plan, list_recent_plans
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


class DraftStatusPayload(BaseModel):
    status: str


class DraftFeedbackPayload(BaseModel):
    feedback: str


class KeywordPayload(BaseModel):
    topic_idx: int
    field: str
    word: str


class ReelsFrameNotePayload(BaseModel):
    note: str = Field(default="")


class ReelsFramePromptPayload(BaseModel):
    prompt: str = Field(default="")


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


@app.get("/api/inbox")
async def inbox(limit: int = Query(default=50, ge=1, le=200), kind: str = ""):
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
