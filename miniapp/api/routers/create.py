from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from bot.agents import generate_content_draft
from bot.services.drafts_store import save_draft
from bot.services.miniapp_generator import build_content_payload, build_reels_payload, is_valid_content_format, is_valid_content_goal
from bot.services.miniapp_presenter import serialize_draft
from bot.services.miniapp_reels import serialize_reels_draft
from config import settings
from ..auth import _require_auth
from ..generation import complete_carousel_generation, complete_reels_generation
from ..models import CreateCarouselPayload, CreateContentPayload, CreateReelsPayload

router = APIRouter()


def _validate_topic(payload) -> str:
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="empty_topic")
    return topic


@router.post("/api/generate/content")
async def generate_content(payload: CreateContentPayload, _: None = Depends(_require_auth)):
    topic = _validate_topic(payload)
    goal_key = payload.goal_key.strip().lower()
    format_key = payload.format_key.strip().lower()

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


@router.post("/api/generate/reels")
async def generate_reels(
    payload: CreateReelsPayload,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    topic = _validate_topic(payload)

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
    background_tasks.add_task(complete_reels_generation, saved.draft_id, topic)
    draft = await serialize_reels_draft(saved.draft_id)
    if not draft:
        raise HTTPException(status_code=500, detail="reels_not_saved")
    return draft


@router.post("/api/generate/carousel")
async def generate_carousel(
    payload: CreateCarouselPayload,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    topic = _validate_topic(payload)

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
    background_tasks.add_task(complete_carousel_generation, saved.draft_id, topic)
    return await serialize_draft(saved)
