from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import urllib.parse
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from telegram import Bot

from bot.agents import generate_content_draft
from bot.agents.planner import generate_plan_sync
from bot.agents.reels_agent import generate_reels_director_sync, generate_reels_scenario_sync
from bot.handlers.carousel import _build_pptx, _format_for_canva, _generate_carousel_sync
from bot.handlers.planner import _parse_plan_entries
from bot.handlers.threads import _format_trends
from bot.services.miniapp_content_review import (
    polish_content_review_draft,
    update_content_review_draft,
)
from bot.services.miniapp_references import enrich_reference_card, get_reference_card, list_reference_cards, update_reference_card
from bot.services.miniapp_plan_actions import normalize_plan_format, normalize_plan_goal
from bot.services.reels_assets import ASSETS_DIR, populate_reels_frame_assets, regenerate_reels_frame_asset
from bot.services.carousel_assets import (
    CAROUSEL_ASSETS_DIR,
    delete_carousel_slide_version,
    load_carousel_slide_images,
    populate_carousel_slide_assets,
    regenerate_all_carousel_slide_assets,
    regenerate_carousel_slide_asset,
    select_carousel_slide_version,
    update_carousel_slide_note,
    update_carousel_slide_text,
)
from bot.services.drafts_store import delete_draft, get_draft, list_recent_drafts, update_draft
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
from bot.services.miniapp_presenter import filter_drafts, serialize_draft, serialize_draft_summary
from bot.services.miniapp_reels import (
    build_reels_export_payload,
    list_reels_drafts,
    regenerate_reels_storyboard,
    serialize_reels_draft,
    update_reels_frame_fields,
    update_reels_frame_note,
    update_reels_frame_prompt,
    update_reels_scenario,
)
from bot.services.plans_store import get_plan, list_recent_plans, save_plan
from config import settings


BASE_DIR = Path(__file__).parent
MINIAPP_DIR = BASE_DIR / "miniapp"
STATIC_DIR = MINIAPP_DIR / "static"
REFERENCE_IMAGES_DIR = BASE_DIR / "assets" / "reference_images"


def _asset_version() -> str:
    parts: list[str] = []
    for path in (STATIC_DIR / "app.css", STATIC_DIR / "app.js"):
        if path.exists():
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:10]


def _verify_init_data(init_data: str) -> bool:
    """Validate Telegram WebApp initData using HMAC-SHA256."""
    if os.getenv("AROMA_BYPASS_AUTH") == "1":
        return True
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop("hash", "")
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_hash, received_hash)
    except Exception:
        return False


def _telegram_user_id_from_init_data(init_data: str) -> int | None:
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        raw_user = parsed.get("user", "")
        if not raw_user:
            return None
        payload = json.loads(raw_user)
        user_id = payload.get("id")
        return int(user_id) if user_id is not None else None
    except Exception:
        return None


def _require_auth(x_telegram_init_data: str | None = Header(default=None)) -> None:
    """FastAPI dependency: validate Telegram initData header on mutating endpoints."""
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")


def _resolve_init_data(
    x_telegram_init_data: str | None = Header(default=None),
    init_data: str | None = Query(default=None),
) -> str:
    candidate = x_telegram_init_data or init_data
    if not candidate or not _verify_init_data(candidate):
        raise HTTPException(status_code=403, detail="forbidden")
    return candidate


def _require_reference_access(x_telegram_init_data: str | None = Header(default=None)) -> int:
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data)
    if user_id is None or user_id not in settings.miniapp_aroma_allowed_user_id_set:
        raise HTTPException(status_code=403, detail="reference_access_denied")
    return user_id


app = FastAPI()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="miniapp-static")
app.mount("/generated/reels_assets", StaticFiles(directory=ASSETS_DIR), name="reels-generated-assets")
app.mount("/generated/carousel_assets", StaticFiles(directory=CAROUSEL_ASSETS_DIR), name="carousel-generated-assets")

# Ensure directory exists to prevent Starlette from crashing on mount
REFERENCE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/reference-images", StaticFiles(directory=REFERENCE_IMAGES_DIR), name="reference-images")


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
    editor_notes: str = Field(default="")


class KeywordPayload(BaseModel):
    topic_idx: int
    field: str
    word: str


class ReelsFrameNotePayload(BaseModel):
    note: str = Field(default="")


class ReelsFramePromptPayload(BaseModel):
    prompt: str = Field(default="")


class ReelsScenarioPayload(BaseModel):
    scenario: str = Field(default="")
    concept: str = Field(default="")


class ReelsFrameFieldsPayload(BaseModel):
    scene: str = Field(default="")
    angle: str = Field(default="")
    timecode: str = Field(default="")


class CreateContentPayload(BaseModel):
    topic: str = Field(default="")
    goal_key: str = Field(default="")
    format_key: str = Field(default="")


class CreateReelsPayload(BaseModel):
    topic: str = Field(default="")


class CreateCarouselPayload(BaseModel):
    topic: str = Field(default="")


class CarouselSlideRegeneratePayload(BaseModel):
    note: str | None = Field(default=None)


class CarouselSlideTextPayload(BaseModel):
    text: str = Field(default="")


class CarouselSlideNotePayload(BaseModel):
    note: str = Field(default="")


class PlanGeneratePayload(BaseModel):
    entry_index: int


class AromaCardPayload(BaseModel):
    description: str = Field(default="")
    questions: str = Field(default="")
    nps_effect: str = Field(default="")
    therapeutic_properties: str = Field(default="")
    psychological_properties: str = Field(default="")
    history: str = Field(default="")
    volatility: str = Field(default="")
    botanical_family: str = Field(default="")
    origin_countries: str = Field(default="")
    extraction_method: str = Field(default="")
    key: str = Field(default="")
    resource_values: dict[str, str] = Field(default_factory=dict)


async def _set_generation_state(
    draft_id: str,
    *,
    pending: bool,
    stage: str = "",
    message: str = "",
    error: str = "",
) -> None:
    draft = await get_draft(draft_id)
    if not draft:
        return
    payload = dict(draft.payload or {})
    payload["generation_pending"] = pending
    payload["generation_stage"] = stage
    payload["generation_message"] = message
    if error:
        payload["generation_error"] = error
    else:
        payload.pop("generation_error", None)
    await update_draft(draft_id, payload=payload, status="draft")


async def _complete_carousel_generation(draft_id: str, topic: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        slides, img_prompts, arc = await loop.run_in_executor(None, _generate_carousel_sync, topic)
        if not slides:
            raise RuntimeError("carousel_generation_failed")
        draft = await get_draft(draft_id)
        if not draft:
            return
        payload = dict(draft.payload or {})
        payload.update(
            {
                "slides": slides,
                "img_prompts": img_prompts,
                "arc": arc,
                "slide_images": [],
                "slide_image_versions": [],
                "img_prompt_notes": [],
                "images_ready": 0,
                "generation_pending": True,
                "generation_stage": "images",
                "generation_message": "Генерирую картинки для слайдов.",
            }
        )
        await update_draft(draft_id, payload=payload, status="draft")
        await populate_carousel_slide_assets(draft_id)
        await _set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await _set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось закончить генерацию карусели. Попробуйте ещё раз.",
            error=str(exc),
        )


async def _complete_reels_generation(draft_id: str, topic: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        scenario = await loop.run_in_executor(None, generate_reels_scenario_sync, topic)
        await _set_generation_state(
            draft_id,
            pending=True,
            stage="storyboard",
            message="Собираю раскадровку рилса.",
        )
        frames = await loop.run_in_executor(None, generate_reels_director_sync, topic, scenario)
        draft = await get_draft(draft_id)
        if not draft:
            return
        payload = dict(draft.payload or {})
        payload.update(
            {
                "scenario": scenario,
                "storyboard": [
                    {
                        "timecode": frame.timecode,
                        "scene": frame.scene,
                        "angle": frame.angle,
                        "gemini_prompt": frame.gemini_prompt,
                        "review_note": "",
                        "prompt_revisions": [],
                        "current_asset": {},
                        "asset_revisions": [],
                    }
                    for frame in frames
                ],
                "images_ready": 0,
                "generation_pending": True,
                "generation_stage": "images",
                "generation_message": "Генерирую кадры для рилса.",
            }
        )
        await update_draft(draft_id, payload=payload, status="draft")
        await populate_reels_frame_assets(draft_id)
        await _set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await _set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось закончить генерацию рилса. Попробуйте ещё раз.",
            error=str(exc),
        )


async def _complete_carousel_regenerate_all(draft_id: str) -> None:
    try:
        await regenerate_all_carousel_slide_assets(draft_id)
        await _set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await _set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось перегенерировать все картинки. Попробуйте ещё раз.",
            error=str(exc),
        )


async def _complete_reels_regenerate_all(draft_id: str) -> None:
    try:
        await populate_reels_frame_assets(draft_id, overwrite_existing=True)
        await _set_generation_state(draft_id, pending=False)
    except Exception as exc:
        await _set_generation_state(
            draft_id,
            pending=False,
            stage="error",
            message="Не удалось перегенерировать кадры. Попробуйте ещё раз.",
            error=str(exc),
        )


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (MINIAPP_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("__ASSET_VERSION__", _asset_version())
    return HTMLResponse(
        content=html,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


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
    _: None = Depends(_require_auth),
):
    records = await list_recent_drafts(limit=200)
    filtered = await filter_drafts(
        records,
        kind=kind,
        status=status,
        feedback=feedback,
        query=query,
    )
    return {
        "items": [await serialize_draft_summary(record) for record in filtered[:limit]],
        "total": len(filtered),
    }


@app.get("/api/drafts/{draft_id}")
async def draft_detail(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(draft)


@app.post("/api/drafts/{draft_id}/status")
async def update_status(draft_id: str, payload: DraftStatusPayload, _: None = Depends(_require_auth)):
    status = payload.status.strip().lower()
    if status not in {"draft", "in_review", "approved", "published", "rejected"}:
        raise HTTPException(status_code=400, detail="invalid_status")
    draft = await update_draft(draft_id, status=status)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(draft)


@app.delete("/api/drafts/{draft_id}")
async def remove_draft(draft_id: str, _: None = Depends(_require_auth)):
    deleted = await delete_draft(draft_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return {"ok": True, "draft_id": draft_id}


@app.post("/api/drafts/{draft_id}/feedback")
async def update_feedback(draft_id: str, payload: DraftFeedbackPayload, _: None = Depends(_require_auth)):
    feedback = payload.feedback.strip().lower()
    if feedback not in {"", "worked", "missed"}:
        raise HTTPException(status_code=400, detail="invalid_feedback")
    draft = await update_draft(draft_id, feedback=feedback)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(draft)


@app.post("/api/drafts/{draft_id}/content")
async def update_content(draft_id: str, payload: DraftContentPayload, _: None = Depends(_require_auth)):
    updated = await update_content_review_draft(
        draft_id,
        topic=payload.topic,
        angle=payload.angle,
        hook=payload.hook,
        caption=payload.caption,
        cta=payload.cta,
        hashtags=payload.hashtags,
        visual_prompt=payload.visual_prompt,
        editor_notes=payload.editor_notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="content_draft_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(draft)


@app.post("/api/drafts/{draft_id}/content/polish")
async def polish_content(draft_id: str, _: None = Depends(_require_auth)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")
    updated = await polish_content_review_draft(draft_id)
    if not updated:
        raise HTTPException(status_code=404, detail="content_draft_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(draft)


@app.get("/api/status")
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


@app.get("/api/references/access")
async def references_access(x_telegram_init_data: str | None = Header(default=None)):
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        return {"allowed": False}
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data)
    return {
        "allowed": bool(user_id in settings.miniapp_aroma_allowed_user_id_set if user_id is not None else False),
        "user_id": user_id,
    }


@app.get("/api/references/{category}")
async def references_list(category: str, _: int = Depends(_require_reference_access)):
    return {"items": await list_reference_cards(category)}


@app.get("/api/references/{category}/{slug}")
async def reference_detail(category: str, slug: str, _: int = Depends(_require_reference_access)):
    card = await get_reference_card(category, slug)
    if not card:
        raise HTTPException(status_code=404, detail="reference_not_found")
    return card


@app.put("/api/references/{category}/{slug}")
async def reference_update(category: str, slug: str, payload: AromaCardPayload, _: int = Depends(_require_reference_access)):
    card = await update_reference_card(category, slug, payload.model_dump())
    if not card:
        raise HTTPException(status_code=404, detail="reference_not_found")
    return card


@app.post("/api/references/{category}/{slug}/expert-fill")
async def reference_expert_fill(category: str, slug: str, _: int = Depends(_require_reference_access)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")
    card = await enrich_reference_card(category, slug)
    if not card:
        raise HTTPException(status_code=404, detail="reference_not_found")
    return card


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
    saved = await save_draft(
        kind=format_key,
        topic=topic,
        source="/miniapp",
        payload=build_content_payload(draft, goal_key=goal_key, format_key=format_key),
    )
    return await serialize_draft(saved)


@app.post("/api/generate/reels")
async def generate_reels(
    payload: CreateReelsPayload,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")

    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="empty_topic")

    saved = await save_draft(
        kind="reels",
        topic=topic,
        source="/miniapp",
        payload={
            "scenario": "",
            "concept": "",
            "storyboard": [],
            "images_ready": 0,
            "generation_pending": True,
            "generation_stage": "scenario",
            "generation_message": "Собираю сценарий для рилса.",
        },
    )
    background_tasks.add_task(_complete_reels_generation, saved.draft_id, topic)
    draft = await serialize_reels_draft(saved.draft_id)
    if not draft:
        raise HTTPException(status_code=500, detail="reels_not_saved")
    return draft


@app.post("/api/generate/carousel")
async def generate_carousel(
    payload: CreateCarouselPayload,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")

    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="empty_topic")

    saved = await save_draft(
        kind="carousel",
        topic=topic,
        source="/miniapp",
        payload={
            "slides": [],
            "img_prompts": [],
            "arc": "",
            "slide_images": [],
            "slide_image_versions": [],
            "img_prompt_notes": [],
            "images_ready": 0,
            "generation_pending": True,
            "generation_stage": "slides",
            "generation_message": "Собираю структуру карусели.",
        },
    )
    background_tasks.add_task(_complete_carousel_generation, saved.draft_id, topic)
    return await serialize_draft(saved)


@app.get("/api/carousel/{draft_id}")
async def get_carousel(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


@app.post("/api/carousel/{draft_id}/slides/{slide_index}/regenerate")
async def regenerate_carousel_slide(
    draft_id: str,
    slide_index: int,
    payload: CarouselSlideRegeneratePayload,
    _: None = Depends(_require_auth),
):
    updated_payload = await regenerate_carousel_slide_asset(draft_id, slide_index, note=payload.note)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_slide_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


@app.post("/api/carousel/{draft_id}/slides/{slide_index}/text")
async def update_carousel_slide_copy(
    draft_id: str,
    slide_index: int,
    payload: CarouselSlideTextPayload,
    _: None = Depends(_require_auth),
):
    updated_payload = await update_carousel_slide_text(draft_id, slide_index, payload.text)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_slide_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


@app.post("/api/carousel/{draft_id}/slides/{slide_index}/note")
async def update_carousel_slide_review_note(
    draft_id: str,
    slide_index: int,
    payload: CarouselSlideNotePayload,
    _: None = Depends(_require_auth),
):
    updated_payload = await update_carousel_slide_note(draft_id, slide_index, payload.note)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_slide_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


@app.post("/api/carousel/{draft_id}/slides/{slide_index}/versions/{version_index}/select")
async def select_carousel_version(
    draft_id: str,
    slide_index: int,
    version_index: int,
    _: None = Depends(_require_auth),
):
    updated_payload = await select_carousel_slide_version(draft_id, slide_index, version_index)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_version_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


@app.delete("/api/carousel/{draft_id}/slides/{slide_index}/versions/{version_index}")
async def delete_carousel_version(
    draft_id: str,
    slide_index: int,
    version_index: int,
    _: None = Depends(_require_auth),
):
    updated_payload = await delete_carousel_slide_version(draft_id, slide_index, version_index)
    if updated_payload is None:
        raise HTTPException(status_code=404, detail="carousel_version_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(draft)


@app.post("/api/carousel/{draft_id}/regenerate-all")
async def regenerate_carousel_all(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")
    await _set_generation_state(
        draft_id,
        pending=True,
        stage="images",
        message="Перегенерирую все картинки в карусели.",
    )
    background_tasks.add_task(_complete_carousel_regenerate_all, draft_id)
    refreshed = await get_draft(draft_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="carousel_not_found")
    return await serialize_draft(refreshed)


@app.get("/api/carousel/{draft_id}/pptx")
async def carousel_pptx_export(draft_id: str, _: str = Depends(_resolve_init_data)):
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "carousel":
        raise HTTPException(status_code=404, detail="carousel_not_found")
    slides = list(draft.payload.get("slides", []))
    images = load_carousel_slide_images(draft_id, list(draft.payload.get("slide_images", [])))
    pptx_bytes = await asyncio.get_running_loop().run_in_executor(None, _build_pptx, slides, images or None)
    return StreamingResponse(
        iter([pptx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename=\"carousel_{draft_id}.pptx\"'},
    )


def _draft_chat_message(draft) -> str:
    payload = dict(draft.payload or {})
    if draft.kind == "carousel":
        slides = [str(item).strip() for item in payload.get("slides", []) if str(item).strip()]
        slides_text = "\n\n".join(f"{idx + 1}. {slide}" for idx, slide in enumerate(slides))
        return f"Карусель\n\nТема: {draft.topic}\n\n{slides_text}".strip()
    if draft.kind == "reels":
        scenario = str(payload.get("scenario", "")).strip()
        return f"Рилс\n\nТема: {draft.topic}\n\n{scenario}".strip()
    text = str(payload.get("caption") or payload.get("hook") or payload.get("angle") or "").strip()
    return f"{draft.kind.title()}\n\nТема: {draft.topic}\n\n{text}".strip()


@app.post("/api/drafts/{draft_id}/send")
async def send_draft_to_chat(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if not settings.telegram_bot_token or not settings.report_target_chat_id:
        raise HTTPException(status_code=400, detail="telegram_not_configured")
    bot = Bot(token=settings.telegram_bot_token)
    await bot.send_message(chat_id=settings.report_target_chat_id, text=_draft_chat_message(draft))
    return {"ok": True}


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


@app.get("/api/inbox")
async def inbox(limit: int = Query(default=50, ge=1, le=200), kind: str = "", _: None = Depends(_require_auth)):
    items = await list_inbox_items(limit=limit, kind_filter=kind)
    return {
        "items": items,
        "total": len(items),
        "kind": kind.strip().lower() or "all",
    }


@app.get("/api/plans")
async def plans(limit: int = Query(default=20, ge=1, le=100), _: None = Depends(_require_auth)):
    records = await list_recent_plans(limit=limit)
    return {
        "items": [await serialize_plan(record) for record in records],
        "total": len(records),
    }


@app.get("/api/plans/{plan_id}")
async def plan_detail(plan_id: str, _: None = Depends(_require_auth)):
    record = await get_plan(plan_id)
    if not record:
        raise HTTPException(status_code=404, detail="plan_not_found")
    return await serialize_plan(record)


@app.post("/api/plans/{plan_id}/generate")
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
        scenario = await loop.run_in_executor(None, generate_reels_scenario_sync, topic)
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


@app.get("/api/reels")
async def reels(limit: int = Query(default=30, ge=1, le=100), _: None = Depends(_require_auth)):
    items = await list_reels_drafts(limit=limit)
    return {
        "items": items,
        "total": len(items),
    }


@app.get("/api/reels/{draft_id}")
async def reels_detail(draft_id: str, _: None = Depends(_require_auth)):
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@app.get("/api/reels/{draft_id}/export")
async def reels_export(draft_id: str, _: None = Depends(_require_auth)):
    payload = await build_reels_export_payload(draft_id)
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
    draft = await update_reels_frame_note(draft_id, frame_index, payload.note)
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
    draft = await update_reels_frame_prompt(draft_id, frame_index, prompt)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_frame_not_found")
    return draft


@app.post("/api/reels/{draft_id}/frames/{frame_index}/regenerate")
async def reels_frame_regenerate(
    draft_id: str,
    frame_index: int,
    _: None = Depends(_require_auth),
):
    regen_payload = await regenerate_reels_frame_asset(draft_id, frame_index)
    if not regen_payload:
        raise HTTPException(status_code=503, detail="reels_frame_regenerate_failed")
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@app.post("/api/reels/{draft_id}/scenario")
async def reels_scenario_update(
    draft_id: str,
    payload: ReelsScenarioPayload,
    _: None = Depends(_require_auth),
):
    draft = await update_reels_scenario(draft_id, payload.scenario, payload.concept)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@app.post("/api/reels/{draft_id}/storyboard/regenerate")
async def reels_storyboard_regenerate(
    draft_id: str,
    _: None = Depends(_require_auth),
):
    draft = await regenerate_reels_storyboard(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@app.post("/api/reels/{draft_id}/frames/regenerate-all")
async def reels_frames_regenerate_all(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels":
        raise HTTPException(status_code=404, detail="reels_not_found")
    await _set_generation_state(
        draft_id,
        pending=True,
        stage="images",
        message="Перегенерирую все кадры рилса.",
    )
    background_tasks.add_task(_complete_reels_regenerate_all, draft_id)
    draft = await serialize_reels_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="reels_not_found")
    return draft


@app.post("/api/reels/{draft_id}/frames/{frame_index}/fields")
async def reels_frame_fields(
    draft_id: str,
    frame_index: int,
    payload: ReelsFrameFieldsPayload,
    _: None = Depends(_require_auth),
):
    draft = await update_reels_frame_fields(
        draft_id,
        frame_index,
        scene=payload.scene,
        angle=payload.angle,
        timecode=payload.timecode,
    )
    if not draft:
        raise HTTPException(status_code=404, detail="reels_frame_not_found")
    return draft


@app.get("/api/keywords")
async def keywords(_: None = Depends(_require_auth)):
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
