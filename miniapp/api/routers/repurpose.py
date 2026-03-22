"""Repurpose Engine API router."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from bot.services.drafts_store import get_draft, update_draft
from bot.services.miniapp_presenter import serialize_draft

from ..auth import TeamContext, _require_auth, _resolve_team_context, require_tier

logger = logging.getLogger(__name__)
router = APIRouter()


class RepurposeStartRequest(BaseModel):
    source_draft_id: str = Field(..., min_length=1)
    formats: list[str] = Field(..., min_length=1, max_length=5)


@router.post("/api/repurpose/start", dependencies=[Depends(require_tier("expert"))])
async def start_repurpose(
    body: RepurposeStartRequest,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Start repurposing a draft into multiple formats."""
    from db.models import RepurposeGroupModel
    from db.session import AsyncSessionLocal
    from miniapp.api.generation.repurpose import complete_repurpose_generation

    source = await get_draft(body.source_draft_id)
    if not source:
        raise HTTPException(status_code=404, detail="source_draft_not_found")

    valid_formats = {"carousel", "reels_v2", "threads_series", "content_series", "instagram", "telegram"}
    for fmt in body.formats:
        if fmt not in valid_formats:
            raise HTTPException(status_code=400, detail=f"invalid_format: {fmt}")

    group_id = uuid.uuid4().hex[:12]

    async with AsyncSessionLocal() as session:
        group = RepurposeGroupModel(
            group_id=group_id,
            team_id=ctx.team_id,
            source_draft_id=body.source_draft_id,
            status="pending",
            target_drafts=[{"format": f, "status": "pending"} for f in body.formats],
        )
        session.add(group)
        await session.commit()

    background_tasks.add_task(
        complete_repurpose_generation,
        group_id, body.source_draft_id, body.formats, ctx.team_id, ctx.telegram_id,
    )

    return {"group_id": group_id, "status": "pending", "formats": body.formats}


@router.get("/api/repurpose/group/{group_id}", dependencies=[Depends(_require_auth)])
async def get_repurpose_group(group_id: str):
    """Get repurpose group status and all created drafts."""
    from sqlalchemy import select

    from db.models import RepurposeGroupModel
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RepurposeGroupModel).where(RepurposeGroupModel.group_id == group_id)
        )
        group = result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="group_not_found")

        drafts = []
        for entry in (group.target_drafts or []):
            draft_id = entry.get("draft_id")
            if draft_id:
                d = await get_draft(draft_id)
                if d:
                    drafts.append(await serialize_draft(d))

        return {
            "group_id": group.group_id,
            "source_draft_id": group.source_draft_id,
            "status": group.status,
            "core_message": group.core_message,
            "key_points": group.key_points or [],
            "target_drafts": group.target_drafts or [],
            "drafts": drafts,
            "created_at": group.created_at.isoformat() if group.created_at else "",
        }


@router.post("/api/repurpose/group/{group_id}/approve-all", dependencies=[Depends(require_tier("expert"))])
async def approve_all_repurposed(group_id: str):
    """Approve all drafts in the repurpose group."""
    from sqlalchemy import select

    from db.models import RepurposeGroupModel
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RepurposeGroupModel).where(RepurposeGroupModel.group_id == group_id)
        )
        group = result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="group_not_found")

        approved_count = 0
        for entry in (group.target_drafts or []):
            draft_id = entry.get("draft_id")
            if draft_id:
                await update_draft(draft_id, status="approved")
                approved_count += 1

        group.status = "approved"
        await session.commit()

    return {"ok": True, "approved": approved_count}
