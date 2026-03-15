from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from bot.agents import generate_content_draft
from bot.services.drafts_store import save_draft
from bot.services.miniapp_generator import build_content_payload, build_threads_series_payload, is_valid_content_format, is_valid_content_goal
from bot.services.miniapp_presenter import serialize_draft
from bot.services.miniapp_reels import serialize_reels_draft
from config import settings
from ..auth import _check_content_limit, _require_auth, require_tier
from ..generation import complete_carousel_generation, complete_reels_v2_generation
from ..models import CreateCarouselPayload, CreateContentPayload, CreateReelsV2Payload, ThreadsSeriesCreateRequest

router = APIRouter()


def _validate_topic(payload) -> str:
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="empty_topic")
    return topic


@router.post("/api/generate/content", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
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


@router.post("/api/generate/threads-series", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
async def generate_threads_series(payload: ThreadsSeriesCreateRequest, _: None = Depends(_require_auth)):
    topic = _validate_topic(payload)
    goal_key = payload.goal_key.strip().lower() or "trust"
    emotion = payload.emotion.strip().lower()

    if not is_valid_content_goal(goal_key):
        raise HTTPException(status_code=400, detail="invalid_goal")

    draft = await generate_content_draft(topic, goal_key, "threads_series")
    saved = await save_draft(
        kind="threads_series",
        topic=topic,
        source="/miniapp",
        payload=build_threads_series_payload(draft, goal_key=goal_key, emotion=emotion),
    )
    return await serialize_draft(saved)


@router.post("/api/generate/reels", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
async def generate_reels(
    payload: CreateReelsV2Payload,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_auth),
):
    topic = _validate_topic(payload)
    goal = payload.goal.strip().lower() or "trust"
    emotion = payload.emotion.strip().lower() or "calm"

    saved = await save_draft(
        kind="reels_v2",
        topic=topic,
        source="/miniapp",
        payload={
            "goal": goal,
            "emotion": emotion,
            "concept": "",
            "hook": "",
            "scenario": "",
            "caption": "",
            "music_mood": "",
            "frames": [],
            "images_ready": 0,
            "approved": False,
            "shooting_deadline_days": 0,
            "feedback": {},
            "generation_pending": True,
            "generation_stage": "concept",
            "generation_message": "Собираю концепцию рилса.",
        },
    )
    background_tasks.add_task(complete_reels_v2_generation, saved.draft_id, topic, goal, emotion)
    draft = await serialize_reels_draft(saved.draft_id)
    if not draft:
        raise HTTPException(status_code=500, detail="reels_not_saved")
    return draft


@router.post("/api/generate/carousel", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
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
