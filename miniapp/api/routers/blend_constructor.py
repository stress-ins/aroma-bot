"""Blend Constructor — AI-powered blend creation with expert + doctor review."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from miniapp.api.auth import _require_auth, _resolve_telegram_id

router = APIRouter()


class BlendConstructRequest(BaseModel):
    brief: str
    effects: list[str] = []
    speed: str = "medium"
    application: str = "diffuser"
    contraindications: str = ""
    custom_oils: list[str] = []


class BlendConstructResult(BaseModel):
    title: str
    oils: list[dict]
    total_drops: int
    profile: dict
    expert_note: str
    doctor_note: str
    safety_status: str
    restrictions: list[dict]
    incompatible_oils: list[dict]
    application_guide: str
    tags: list[str]


@router.post("/api/blend-constructor/construct", response_model=BlendConstructResult)
async def construct_blend(body: BlendConstructRequest, _: None = Depends(_require_auth)):
    if not body.brief.strip():
        raise HTTPException(status_code=400, detail="brief is required")
    from miniapp.api.generation import generate_blend_construct
    result = await generate_blend_construct(body)
    return result


@router.post("/api/blend-constructor/adjust", response_model=BlendConstructResult)
async def adjust_blend(body: BlendConstructRequest, _: None = Depends(_require_auth)):
    if not body.brief.strip():
        raise HTTPException(status_code=400, detail="brief is required")
    if not body.custom_oils:
        raise HTTPException(status_code=400, detail="custom_oils is required for adjust")
    from miniapp.api.generation import generate_blend_construct
    result = await generate_blend_construct(body)
    return result


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
async def create_saved_blend(body: SaveBlendRequest, telegram_id: int = Depends(_resolve_telegram_id)):
    from bot.services.saved_blends_store import save_blend
    return await save_blend(telegram_id=telegram_id, title=body.title, brief=body.brief, tags=body.tags, oils=body.oils, total_drops=body.total_drops, profile=body.profile, expert_note=body.expert_note, application_guide=body.application_guide, safety_status=body.safety_status)


@router.get("/api/blend-constructor/saved")
async def get_saved_blends(telegram_id: int = Depends(_resolve_telegram_id)):
    from bot.services.saved_blends_store import list_saved_blends
    items = await list_saved_blends(telegram_id)
    return {"items": items, "total": len(items)}


@router.delete("/api/blend-constructor/saved/{saved_id}")
async def remove_saved_blend(saved_id: str, telegram_id: int = Depends(_resolve_telegram_id)):
    from bot.services.saved_blends_store import delete_saved_blend
    deleted = await delete_saved_blend(telegram_id, saved_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="saved_blend_not_found")
    return {"deleted": saved_id}
