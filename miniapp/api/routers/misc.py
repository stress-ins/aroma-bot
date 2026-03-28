from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
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
from bot.services.brand_settings_store import get_brand_settings, update_brand_settings
from ..auth import _require_auth, issue_sse_token

router = APIRouter()


@router.post("/api/auth/sse-token")
async def create_sse_token(
    x_telegram_init_data: str | None = Header(default=None),
    _: None = Depends(_require_auth),
):
    """Exchange valid Telegram initData (header) for a short-lived opaque SSE token."""
    token = issue_sse_token(x_telegram_init_data or "")
    return {"token": token}


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



class ImageModelPayload(BaseModel):
    image_model_carousel: str | None = None
    image_model_img2img: str | None = None
    image_model_reels: str | None = None
    reels_auto_images: bool | None = None


class ThemePayload(BaseModel):
    theme: str


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


@router.get("/readyz")
async def readyz():
    from miniapp_server import _ready
    if not _ready:
        return JSONResponse({"ok": False, "reason": "starting"}, status_code=503)
    return JSONResponse({"ok": True})


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






ALLOWED_CAROUSEL_MODELS = {"gpt-image/1.5-text-to-image", "google/nano-banana"}
ALLOWED_IMG2IMG_MODELS = {"google/nano-banana-edit"}
ALLOWED_REELS_MODELS = {"gpt-image/1.5-text-to-image", "flux-2/pro-text-to-image", "google/nano-banana"}


@router.get("/api/preferences/image-models")
async def get_image_models(_: None = Depends(_require_auth)):
    bs = await get_brand_settings()
    return {
        "image_model_carousel": bs.image_model_carousel or "gpt-image/1.5-text-to-image",
        "image_model_img2img": bs.image_model_img2img or "google/nano-banana-edit",
        "image_model_reels": bs.image_model_reels or "gpt-image/1.5-text-to-image",
        "reels_auto_images": bs.reels_auto_images if bs.reels_auto_images is not None else False,
        "options": {
            "carousel": [
                {"value": "gpt-image/1.5-text-to-image", "label": "GPT Image 1.5"},
                {"value": "google/nano-banana", "label": "Nano Banana"},
            ],
            "img2img": [
                {"value": "google/nano-banana-edit", "label": "Nano Banana Edit"},
            ],
            "reels": [
                {"value": "gpt-image/1.5-text-to-image", "label": "GPT Image 1.5"},
                {"value": "flux-2/pro-text-to-image", "label": "Flux 2 Pro"},
                {"value": "google/nano-banana", "label": "Nano Banana"},
            ],
        },
    }


@router.put("/api/preferences/image-models")
async def update_image_models(payload: ImageModelPayload, _: None = Depends(_require_auth)):
    updates: dict = {}
    if payload.image_model_carousel is not None and payload.image_model_carousel in ALLOWED_CAROUSEL_MODELS:
        updates["image_model_carousel"] = payload.image_model_carousel
    if payload.image_model_img2img is not None and payload.image_model_img2img in ALLOWED_IMG2IMG_MODELS:
        updates["image_model_img2img"] = payload.image_model_img2img
    if payload.image_model_reels is not None and payload.image_model_reels in ALLOWED_REELS_MODELS:
        updates["image_model_reels"] = payload.image_model_reels
    if payload.reels_auto_images is not None:
        updates["reels_auto_images"] = payload.reels_auto_images
    if updates:
        await update_brand_settings(**updates)
    bs = await get_brand_settings()
    return {
        "image_model_carousel": bs.image_model_carousel or "gpt-image/1.5-text-to-image",
        "image_model_img2img": bs.image_model_img2img or "google/nano-banana-edit",
        "image_model_reels": bs.image_model_reels or "gpt-image/1.5-text-to-image",
        "reels_auto_images": bs.reels_auto_images if bs.reels_auto_images is not None else False,
    }


VALID_THEMES = {"terracotta", "racing-green", "champagne", "violet", "teal", "raspberry"}


@router.get("/api/preferences/theme")
async def get_theme(_: None = Depends(_require_auth)):
    bs = await get_brand_settings()
    return {"theme": bs.theme or "terracotta"}


@router.patch("/api/preferences/theme")
async def update_theme(payload: ThemePayload, _: None = Depends(_require_auth)):
    if payload.theme not in VALID_THEMES:
        raise HTTPException(status_code=400, detail="Invalid theme")
    await update_brand_settings(theme=payload.theme)
    return {"theme": payload.theme}


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
