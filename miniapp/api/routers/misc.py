from __future__ import annotations

import json
import uuid
from pathlib import Path

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

_TODO_PATH = Path("data/todo.json")


class ForbiddenPhrasePayload(BaseModel):
    phrase: str


class TodoAddPayload(BaseModel):
    text: str


class TodoRemovePayload(BaseModel):
    id: str


def _load_todo() -> list[dict]:
    if not _TODO_PATH.exists():
        return []
    return json.loads(_TODO_PATH.read_text(encoding="utf-8"))


def _save_todo(items: list[dict]) -> None:
    _TODO_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TODO_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


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


@router.get("/api/todo")
async def get_todo(_: None = Depends(_require_auth)):
    return {"items": _load_todo()}


@router.post("/api/todo/add")
async def add_todo(payload: TodoAddPayload, _: None = Depends(_require_auth)):
    text = payload.text.strip()
    if not text:
        return {"items": _load_todo()}
    items = _load_todo()
    items.append({"id": str(uuid.uuid4()), "text": text})
    _save_todo(items)
    return {"items": items}


@router.post("/api/todo/remove")
async def remove_todo(payload: TodoRemovePayload, _: None = Depends(_require_auth)):
    items = [item for item in _load_todo() if item.get("id") != payload.id]
    _save_todo(items)
    return {"items": items}
