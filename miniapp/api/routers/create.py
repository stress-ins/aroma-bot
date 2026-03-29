from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

import logging

from bot.agents.content import suggest_topics
from bot.services.drafts_store import list_recent_drafts, save_draft
from bot.services.miniapp_generator import is_valid_content_format, is_valid_content_goal

logger = logging.getLogger(__name__)
from bot.services.miniapp_presenter import serialize_draft
from bot.services.miniapp_reels import serialize_reels_draft
from config import settings
from ..auth import TeamContext, _check_content_limit, _require_auth, _resolve_team_context, require_tier
from ..generation import complete_carousel_generation, complete_content_generation, complete_reels_lightweight_generation, complete_reels_v2_generation, complete_series_generation, complete_threads_series_generation, complete_youtube_generation, complete_youtube_generate_thumbnail, complete_youtube_generate_metadata, complete_youtube_regen_script
from ..models import ContentSeriesCreateRequest, CreateCarouselPayload, CreateContentPayload, CreateReelsV2Payload, CreateYouTubePayload, YouTubeThumbnailPayload, SuggestTopicsRequest, ThreadsSeriesCreateRequest

router = APIRouter()


def _validate_topic(payload) -> str:
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="empty_topic")
    return topic


def _extract_blend_context(payload) -> dict | None:
    bc = getattr(payload, "blend_context", None)
    return bc.model_dump() if bc else None


def _extract_daily_oil_context(payload) -> dict | None:
    doc = getattr(payload, "daily_oil_context", None)
    return doc.model_dump() if doc else None


def _enrich_topic_with_daily_oil(topic: str, doc: dict | None) -> str:
    """Prepend daily oil context to topic for richer generation."""
    if not doc or not doc.get("oil_name"):
        return topic
    parts = [f"Масло дня: {doc['oil_name']}."]
    if doc.get("reason"):
        parts.append(f"Почему сегодня: {doc['reason']}")
    if doc.get("fact"):
        parts.append(f"Факт: {doc['fact']}")
    if doc.get("daily_practice"):
        parts.append(f"Практика: {doc['daily_practice']}")
    context_block = " ".join(parts)
    return f"{context_block}\n\nТема: {topic}"


async def _fetch_brand_profile(team_id: str | None) -> dict:
    """Fetch brand username and avatar from connected Instagram/Threads account.

    Returns dict with brand_username and optionally brand_avatar_path.
    """
    from bot.services.mentions_store import get_token, get_token_for_team
    from pathlib import Path
    import httpx

    result: dict = {}

    # Try Instagram first, then Threads
    for platform in ("instagram", "threads"):
        try:
            if team_id:
                uname_rec = await get_token_for_team(f"{platform}_username", team_id)
            else:
                uname_rec = await get_token(f"{platform}_username")
            if uname_rec and uname_rec.access_token:
                result["brand_username"] = uname_rec.access_token
                break
        except Exception:
            continue

    if not result.get("brand_username"):
        return result

    # Try to fetch avatar from Threads profile
    try:
        if team_id:
            th_token = await get_token_for_team("threads", team_id)
        else:
            th_token = await get_token("threads")
        if th_token and th_token.access_token:
            from bot.services.threads_api import ThreadsAPI
            api = ThreadsAPI(th_token.access_token)
            profile = api.get_me()
            pic_url = profile.get("threads_profile_picture_url")
            if pic_url:
                avatars_dir = Path("data/avatars")
                avatars_dir.mkdir(parents=True, exist_ok=True)
                avatar_path = avatars_dir / f"{result['brand_username']}.jpg"
                async with httpx.AsyncClient() as client:
                    resp = await client.get(pic_url, timeout=15)
                    if resp.status_code == 200:
                        avatar_path.write_bytes(resp.content)
                        result["brand_avatar_path"] = str(avatar_path.resolve())
    except Exception:
        logger.debug("Failed to fetch brand avatar", exc_info=True)

    # Fallback: use manually uploaded team avatar
    if not result.get("brand_avatar_path") and team_id:
        from pathlib import Path as _P
        team_avatar = _P("data/avatars") / f"team_{team_id}.jpg"
        if team_avatar.exists():
            result["brand_avatar_path"] = str(team_avatar.resolve())

    return result




@router.post("/api/suggest-topics", dependencies=[Depends(require_tier("expert"))])
async def api_suggest_topics(payload: SuggestTopicsRequest):
    used_topics: list[str] = []
    for status in ("approved", "published"):
        drafts = await list_recent_drafts(limit=200, status=status, newest_first=True)
        used_topics.extend(d.topic for d in drafts if d.topic)
    topics = await suggest_topics(payload.goal_key, payload.format_key, used_topics)
    return {"topics": topics}


@router.post("/api/generate/content", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
async def generate_content(
    payload: CreateContentPayload,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    topic = _validate_topic(payload)
    goal_key = payload.goal_key.strip().lower()
    format_key = payload.format_key.strip().lower()

    if not is_valid_content_goal(goal_key):
        raise HTTPException(status_code=400, detail="invalid_goal")
    if not is_valid_content_format(format_key):
        raise HTTPException(status_code=400, detail="invalid_format")

    bc = _extract_blend_context(payload)
    doc = _extract_daily_oil_context(payload)
    enriched_topic = _enrich_topic_with_daily_oil(topic, doc)
    stub_payload: dict = {
        "generation_pending": True,
        "generation_stage": "content",
        "generation_message": "Собираю черновик.",
        "goal_key": goal_key,
        "format_key": format_key,
    }
    if bc:
        stub_payload["blend_context"] = bc
    if doc:
        stub_payload["daily_oil_context"] = doc
    saved = await save_draft(
        kind=format_key,
        topic=topic,
        source="/miniapp",
        payload=stub_payload,
        team_id=ctx.team_id,
        created_by=ctx.telegram_id,
    )
    practice_focus = getattr(payload, "practice_focus", "aroma") or "aroma"
    background_tasks.add_task(complete_content_generation, saved.draft_id, enriched_topic, goal_key, format_key, bc, practice_focus=practice_focus)
    return await serialize_draft(saved)


@router.post("/api/generate/threads-series", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
async def generate_threads_series(
    payload: ThreadsSeriesCreateRequest,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    topic = _validate_topic(payload)
    goal_key = payload.goal_key.strip().lower() or "trust"
    emotion = payload.emotion.strip().lower()

    if not is_valid_content_goal(goal_key):
        raise HTTPException(status_code=400, detail="invalid_goal")

    bc = _extract_blend_context(payload)
    doc = _extract_daily_oil_context(payload)
    enriched_topic = _enrich_topic_with_daily_oil(topic, doc)
    stub_payload: dict = {
        "generation_pending": True,
        "generation_stage": "content",
        "generation_message": "Собираю серию постов.",
        "goal": goal_key,
        "emotion": emotion,
        "threads_posts": [],
    }
    if bc:
        stub_payload["blend_context"] = bc
    if doc:
        stub_payload["daily_oil_context"] = doc
    saved = await save_draft(
        kind="threads_series",
        topic=topic,
        source="/miniapp",
        payload=stub_payload,
        team_id=ctx.team_id,
        created_by=ctx.telegram_id,
    )
    background_tasks.add_task(complete_threads_series_generation, saved.draft_id, enriched_topic, goal_key, emotion, bc, team_id=ctx.team_id)
    return await serialize_draft(saved)


@router.post("/api/generate/reels", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
async def generate_reels(
    payload: CreateReelsV2Payload,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    topic = _validate_topic(payload)
    goal = payload.goal.strip().lower() or "trust"
    emotion = payload.emotion.strip().lower() or "calm"

    bc = _extract_blend_context(payload)
    doc = _extract_daily_oil_context(payload)
    enriched_topic = _enrich_topic_with_daily_oil(topic, doc)
    lightweight = payload.lightweight
    reels_payload: dict = {
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
    }
    if lightweight:
        reels_payload["lightweight"] = True
    if bc:
        reels_payload["blend_context"] = bc
    if doc:
        reels_payload["daily_oil_context"] = doc
    saved = await save_draft(
        kind="reels_v2",
        topic=topic,
        source="/miniapp",
        payload=reels_payload,
        team_id=ctx.team_id,
        created_by=ctx.telegram_id,
    )
    if lightweight:
        background_tasks.add_task(complete_reels_lightweight_generation, saved.draft_id, enriched_topic, goal, emotion, bc)
    else:
        background_tasks.add_task(complete_reels_v2_generation, saved.draft_id, enriched_topic, goal, emotion, bc)
    draft = await serialize_reels_draft(saved.draft_id)
    if not draft:
        raise HTTPException(status_code=500, detail="reels_not_saved")
    return draft


@router.post("/api/generate/carousel", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
async def generate_carousel(
    payload: CreateCarouselPayload,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    topic = _validate_topic(payload)

    bc = _extract_blend_context(payload)
    doc = _extract_daily_oil_context(payload)
    enriched_topic = _enrich_topic_with_daily_oil(topic, doc)
    carousel_payload: dict = {
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
    }
    if bc:
        carousel_payload["blend_context"] = bc
    if doc:
        carousel_payload["daily_oil_context"] = doc
    layout_style = payload.layout_style if payload.layout_style in ("overlay", "editorial") else "overlay"
    carousel_payload["layout_style"] = layout_style

    # Auto-populate brand profile from connected Instagram/Threads
    brand = await _fetch_brand_profile(ctx.team_id)
    if brand.get("brand_username"):
        carousel_payload["brand_username"] = brand["brand_username"]
    if brand.get("brand_avatar_path"):
        carousel_payload["brand_avatar_path"] = brand["brand_avatar_path"]

    saved = await save_draft(
        kind="carousel",
        topic=topic,
        source="/miniapp",
        payload=carousel_payload,
        team_id=ctx.team_id,
        created_by=ctx.telegram_id,
    )
    background_tasks.add_task(complete_carousel_generation, saved.draft_id, enriched_topic, bc, layout_style)
    return await serialize_draft(saved)


@router.post("/api/generate/content-series", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
async def generate_content_series(
    payload: ContentSeriesCreateRequest,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    topic = _validate_topic(payload)
    goal_key = payload.goal_key.strip().lower() or "trust"
    format_key = payload.format_key.strip().lower() or "instagram"
    post_count = payload.post_count
    template_key = payload.template_key.strip().lower() or "custom"

    if not is_valid_content_goal(goal_key):
        raise HTTPException(status_code=400, detail="invalid_goal")

    stub_payload: dict = {
        "generation_pending": True,
        "generation_stage": "outline",
        "generation_message": "Создаю план серии...",
        "template_key": template_key,
        "post_count": post_count,
        "goal_key": goal_key,
        "format_key": format_key,
        "series_posts": [],
    }
    saved = await save_draft(
        kind="content_series",
        topic=topic,
        source="/miniapp",
        payload=stub_payload,
        team_id=ctx.team_id,
        created_by=ctx.telegram_id,
    )
    background_tasks.add_task(
        complete_series_generation,
        saved.draft_id, topic, goal_key, format_key, post_count, template_key,
    )
    return await serialize_draft(saved)


@router.post("/api/generate/youtube", dependencies=[Depends(require_tier("expert")), Depends(_check_content_limit)])
async def generate_youtube(
    payload: CreateYouTubePayload,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    topic = _validate_topic(payload)
    subformat = payload.subformat.strip().lower()
    if subformat not in ("talking_head", "listicle", "podcast"):
        raise HTTPException(status_code=400, detail="invalid_subformat")

    goal = payload.goal.strip().lower() or "trust"
    emotion = payload.emotion.strip().lower() or "calm"
    duration_target = max(3, min(60, payload.duration_target))

    youtube_payload: dict = {
        "subformat": subformat,
        "goal": goal,
        "emotion": emotion,
        "duration_target": duration_target,
        "title": "",
        "sections": [],
        "broll_map": [],
        "thumbnail": {},
        "metadata": {},
        "generation_pending": True,
        "generation_stage": "script",
        "generation_message": "Создаю сценарий YouTube-видео.",
    }
    saved = await save_draft(
        kind="youtube_video",
        topic=topic,
        source="/miniapp",
        payload=youtube_payload,
        team_id=ctx.team_id,
        created_by=ctx.telegram_id,
    )
    background_tasks.add_task(
        complete_youtube_generation,
        saved.draft_id,
        topic,
        subformat,
        goal,
        emotion,
        duration_target,
        item_count=payload.item_count,
        question_count=payload.question_count,
        guest_description=payload.guest_description,
    )
    return await serialize_draft(saved)


@router.post("/api/youtube/{draft_id}/regen-script", dependencies=[Depends(require_tier("expert"))])
async def youtube_regen_script(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _auth=Depends(_require_auth),
):
    from bot.services.drafts_store import get_draft as _get
    draft = await _get(draft_id)
    if not draft or draft.kind != "youtube_video":
        raise HTTPException(status_code=404, detail="draft_not_found")

    background_tasks.add_task(complete_youtube_regen_script, draft_id)
    return {"ok": True, "draft_id": draft_id}


@router.post("/api/youtube/{draft_id}/thumbnail", dependencies=[Depends(require_tier("expert"))])
async def youtube_thumbnail(
    draft_id: str,
    payload: YouTubeThumbnailPayload,
    background_tasks: BackgroundTasks,
    _auth=Depends(_require_auth),
):
    from bot.services.drafts_store import get_draft as _get
    draft = await _get(draft_id)
    if not draft or draft.kind != "youtube_video":
        raise HTTPException(status_code=404, detail="draft_not_found")

    background_tasks.add_task(
        complete_youtube_generate_thumbnail,
        draft_id,
        mode=payload.mode,
        revision_note=payload.revision_note,
    )
    return {"ok": True, "draft_id": draft_id}


@router.post("/api/youtube/{draft_id}/metadata", dependencies=[Depends(require_tier("expert"))])
async def youtube_metadata(
    draft_id: str,
    background_tasks: BackgroundTasks,
    _auth=Depends(_require_auth),
):
    from bot.services.drafts_store import get_draft as _get
    draft = await _get(draft_id)
    if not draft or draft.kind != "youtube_video":
        raise HTTPException(status_code=404, detail="draft_not_found")

    background_tasks.add_task(complete_youtube_generate_metadata, draft_id)
    return {"ok": True, "draft_id": draft_id}
