"""Blend Constructor — AI-powered blend creation with expert + doctor review."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..auth import TeamContext, _require_auth, _resolve_team_context, _resolve_telegram_id

router = APIRouter()


class BlendConstructRequest(BaseModel):
    brief: str
    effects: list[str] = []
    speed: str = "medium"  # fast | medium | extended
    application: str = "diffuser"  # diffuser | topical | internal | any
    contraindications: str = ""
    custom_oils: list[str] = []
    exclude_oils: list[str] = []
    skip_cache: bool = False


class BlendConstructResult(BaseModel):
    title: str
    oils: list[dict]  # [{name_ru, name_en, drops, role, db_id?, in_db}]
    total_drops: int
    profile: dict  # {focus, energy, creativity, calm} 0-100
    expert_note: str
    doctor_note: str
    safety_status: str  # safe | caution | warning
    restrictions: list[dict]  # [{condition, oils_to_exclude}]
    incompatible_oils: list[dict]  # [{name_ru, reason}]
    application_guide: str
    tags: list[str]


@router.post("/api/blend-constructor/construct", response_model=BlendConstructResult)
async def construct_blend(body: BlendConstructRequest, telegram_id: int = Depends(_resolve_telegram_id)):
    if not body.brief.strip():
        raise HTTPException(status_code=400, detail="brief is required")

    from ..generation import generate_blend_construct

    try:
        result = await generate_blend_construct(body, telegram_id=telegram_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="blend_generation_failed")
    return result


@router.post("/api/blend-constructor/adjust", response_model=BlendConstructResult)
async def adjust_blend(body: BlendConstructRequest, telegram_id: int = Depends(_resolve_telegram_id)):
    """Re-generate blend forcing inclusion of user-specified oils."""
    if not body.brief.strip():
        raise HTTPException(status_code=400, detail="brief is required")
    if not body.custom_oils:
        raise HTTPException(status_code=400, detail="custom_oils is required for adjust")

    from ..generation import generate_blend_construct

    try:
        result = await generate_blend_construct(body, telegram_id=telegram_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="blend_generation_failed")
    return result


# ── Saved Blends ──


class SaveBlendRequest(BaseModel):
    title: str
    brief: str = ""
    tags: list = []
    oils: list = []
    total_drops: int = 0
    profile: dict = {}
    expert_note: str = ""
    application_guide: str = ""
    safety_status: str = "safe"


@router.post("/api/blend-constructor/saved")
async def create_saved_blend(
    body: SaveBlendRequest,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    from bot.services.saved_blends_store import save_blend

    result = await save_blend(
        telegram_id=ctx.telegram_id,
        title=body.title,
        brief=body.brief,
        tags=body.tags,
        oils=body.oils,
        total_drops=body.total_drops,
        profile=body.profile,
        expert_note=body.expert_note,
        application_guide=body.application_guide,
        safety_status=body.safety_status,
        team_id=ctx.team_id,
    )
    return result


@router.get("/api/blend-constructor/saved")
async def get_saved_blends(ctx: TeamContext = Depends(_resolve_team_context)):
    from bot.services.saved_blends_store import list_saved_blends

    items = await list_saved_blends(ctx.telegram_id, team_id=ctx.team_id)
    return {"items": items, "total": len(items)}


@router.get("/api/blend-constructor/saved/{saved_id}")
async def get_saved_blend_detail(
    saved_id: str,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Authenticated endpoint — returns full blend data for owner/team member."""
    from bot.services.saved_blends_store import get_blend_by_id

    blend = await get_blend_by_id(saved_id)
    if not blend:
        raise HTTPException(status_code=404, detail="blend_not_found")
    # Verify ownership or team membership
    if blend.get("telegram_id") != ctx.telegram_id:
        raise HTTPException(status_code=403, detail="not_owner")
    return blend


@router.delete("/api/blend-constructor/saved/{saved_id}")
async def remove_saved_blend(
    saved_id: str,
    telegram_id: int = Depends(_resolve_telegram_id),
):
    from bot.services.saved_blends_store import delete_saved_blend

    deleted = await delete_saved_blend(telegram_id, saved_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="saved_blend_not_found")
    return {"deleted": saved_id}


class BlendOfWeekRequest(BaseModel):
    title: str = ""
    brief: str = ""
    oils: list = []
    total_drops: int = 0
    profile: dict = {}
    expert_note: str = ""
    application_guide: str = ""
    tags: list = []


@router.post("/api/blend-constructor/blend-of-week")
async def blend_of_week(
    body: BlendOfWeekRequest,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Create two drafts from a blend: carousel + threads post."""
    from bot.agents.blend_content_context import build_blend_carousel_narrative, build_blend_of_week_topic
    from bot.services.drafts_store import save_draft
    from bot.services.miniapp_presenter import serialize_draft
    from ..generation import complete_carousel_generation, complete_content_generation

    bc = body.model_dump()
    topic = build_blend_of_week_topic(bc)

    # 1. Create carousel draft.
    # Defaults mirror /api/generate/carousel so regen + analytics see consistent values.
    carousel_goal_key = "trust"
    carousel_emotion = "calm"
    carousel_payload = {
        "generation_pending": True,
        "generation_stage": "content",
        "generation_message": "Собираю карусель для смеси недели.",
        "blend_context": bc,
        "goal_key": carousel_goal_key,
        "emotion": carousel_emotion,
    }
    carousel_draft = await save_draft(
        kind="carousel", topic=topic, source="/miniapp",
        payload=carousel_payload, team_id=ctx.team_id, created_by=ctx.telegram_id,
    )
    background_tasks.add_task(
        complete_carousel_generation,
        carousel_draft.draft_id,
        topic,
        blend_context=bc,
        goal_key=carousel_goal_key,
        emotion=carousel_emotion,
    )

    # 2. Create threads/content draft
    content_payload = {
        "generation_pending": True,
        "generation_stage": "content",
        "generation_message": "Собираю пост для смеси недели.",
        "blend_context": bc,
    }
    content_draft = await save_draft(
        kind="instagram", topic=topic, source="/miniapp",
        payload=content_payload, team_id=ctx.team_id, created_by=ctx.telegram_id,
    )
    background_tasks.add_task(
        complete_content_generation, content_draft.draft_id, topic, "trust", "instagram", blend_context=bc,
    )

    return {
        "carousel_draft_id": carousel_draft.draft_id,
        "content_draft_id": content_draft.draft_id,
        "topic": topic,
    }


@router.get("/api/blend-constructor/shared/{saved_id}")
async def get_shared_blend(saved_id: str):
    """Public endpoint — returns blend data without auth."""
    from bot.services.saved_blends_store import get_blend_by_id

    blend = await get_blend_by_id(saved_id)
    if not blend:
        raise HTTPException(status_code=404, detail="blend_not_found")
    # Strip owner info for public sharing
    blend.pop("telegram_id", None)
    return blend
