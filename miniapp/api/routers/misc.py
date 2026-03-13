from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
from bot.services.forbidden_phrases import (
    load_forbidden_phrases,
    add_forbidden_phrase,
    remove_forbidden_phrase,
)
from ..auth import _require_auth

router = APIRouter()


class ForbiddenPhrasePayload(BaseModel):
    phrase: str


@router.get("/api/status")
async def status(_: None = Depends(_require_auth)):
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


@router.get("/healthz")
async def healthz():
    return JSONResponse({"ok": True, "service": "miniapp"})


@router.get("/api/preferences/forbidden-phrases")
async def get_forbidden_phrases(_: None = Depends(_require_auth)):
    return {"items": load_forbidden_phrases()}


@router.post("/api/preferences/forbidden-phrases/add")
async def add_phrase_endpoint(payload: ForbiddenPhrasePayload, _: None = Depends(_require_auth)):
    return {"items": add_forbidden_phrase(payload.phrase)}


@router.post("/api/preferences/forbidden-phrases/remove")
async def remove_phrase_endpoint(payload: ForbiddenPhrasePayload, _: None = Depends(_require_auth)):
    return {"items": remove_forbidden_phrase(payload.phrase)}
