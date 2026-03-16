"""Blend Constructor — AI-powered blend creation with expert + doctor review."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from miniapp.api.auth import _require_auth

router = APIRouter()


class BlendConstructRequest(BaseModel):
    brief: str
    effects: list[str] = []
    speed: str = "medium"  # fast | medium | extended
    application: str = "diffuser"  # diffuser | topical | internal
    contraindications: str = ""


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
async def construct_blend(body: BlendConstructRequest, _: None = Depends(_require_auth)):
    if not body.brief.strip():
        raise HTTPException(status_code=400, detail="brief is required")

    from miniapp.api.generation import generate_blend_construct

    result = await generate_blend_construct(body)
    return result
