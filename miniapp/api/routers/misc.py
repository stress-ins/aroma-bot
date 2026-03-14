from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, delete

from config import settings
from bot.services.forbidden_phrases import (
    load_forbidden_phrases,
    add_forbidden_phrase,
    remove_forbidden_phrase,
)
from bot.services.policy_engine import (
    PolicyConfig,
    load_policy_config,
    save_policy_config,
)
from db.models import TodoModel
from db.session import AsyncSessionLocal
from ..auth import _require_auth

router = APIRouter()


class ForbiddenPhrasePayload(BaseModel):
    phrase: str


class RewriteAddPayload(BaseModel):
    pattern: str
    replacement: str


class RewriteRemovePayload(BaseModel):
    pattern: str


class PolicyUpdatePayload(BaseModel):
    forbidden_phrases: list[str] | None = None
    soft_rewrites: list[list[str]] | None = None
    per_platform_tone: dict[str, str] | None = None


class TodoAddPayload(BaseModel):
    text: str


class TodoRemovePayload(BaseModel):
    id: str


async def _load_todo() -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TodoModel).order_by(TodoModel.created_at))
        return [{"id": row.todo_id, "text": row.text} for row in result.scalars().all()]


async def _add_todo(text: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        item = TodoModel(todo_id=str(uuid.uuid4()), text=text)
        session.add(item)
        await session.commit()
    return await _load_todo()


async def _remove_todo(todo_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(TodoModel).where(TodoModel.todo_id == todo_id))
        await session.commit()
    return await _load_todo()


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


@router.get("/api/preferences/policy")
async def get_policy(_: None = Depends(_require_auth)):
    cfg = load_policy_config()
    return cfg.to_dict()


@router.put("/api/preferences/policy")
async def update_policy(payload: PolicyUpdatePayload, _: None = Depends(_require_auth)):
    cfg = load_policy_config()
    if payload.forbidden_phrases is not None:
        cfg.forbidden_phrases = payload.forbidden_phrases
    if payload.soft_rewrites is not None:
        cfg.soft_rewrites = payload.soft_rewrites
    if payload.per_platform_tone is not None:
        cfg.per_platform_tone = payload.per_platform_tone
    save_policy_config(cfg)
    return cfg.to_dict()


@router.post("/api/preferences/policy/rewrites/add")
async def add_rewrite(payload: RewriteAddPayload, _: None = Depends(_require_auth)):
    pattern = payload.pattern.strip()
    replacement = payload.replacement.strip()
    if not pattern:
        return load_policy_config().to_dict()
    cfg = load_policy_config()
    # Avoid duplicate patterns
    cfg.soft_rewrites = [r for r in cfg.soft_rewrites if r[0] != pattern]
    cfg.soft_rewrites.append([pattern, replacement])
    save_policy_config(cfg)
    return cfg.to_dict()


@router.post("/api/preferences/policy/rewrites/remove")
async def remove_rewrite(payload: RewriteRemovePayload, _: None = Depends(_require_auth)):
    cfg = load_policy_config()
    cfg.soft_rewrites = [r for r in cfg.soft_rewrites if r[0] != payload.pattern]
    save_policy_config(cfg)
    return cfg.to_dict()


@router.get("/api/todo")
async def get_todo(_: None = Depends(_require_auth)):
    return {"items": await _load_todo()}


@router.post("/api/todo/add")
async def add_todo(payload: TodoAddPayload, _: None = Depends(_require_auth)):
    text = payload.text.strip()
    if not text:
        return {"items": await _load_todo()}
    return {"items": await _add_todo(text)}


@router.post("/api/todo/remove")
async def remove_todo(payload: TodoRemovePayload, _: None = Depends(_require_auth)):
    return {"items": await _remove_todo(payload.id)}
