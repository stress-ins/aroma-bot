"""Tone Adapter API router."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from bot.agents.tone_adapter import VALID_TONES
from bot.services.drafts_store import get_draft, update_draft

from ..auth import _require_auth, require_tier

logger = logging.getLogger(__name__)
router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)


class ToneAdaptRequest(BaseModel):
    tone: str = Field(..., description="Target tone: educational, inspirational, selling, storytelling")


class ToneApplyRequest(BaseModel):
    tone: str = Field(...)


@router.post("/api/drafts/{draft_id}/tone/adapt", dependencies=[Depends(require_tier("expert"))])
async def adapt_tone(draft_id: str, body: ToneAdaptRequest):
    """Adapt draft text to a different tone and save as revision."""
    from bot.agents.tone_adapter import adapt_tone_sync

    if body.tone not in VALID_TONES:
        raise HTTPException(status_code=400, detail=f"invalid_tone. Valid: {VALID_TONES}")

    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")

    payload = draft.payload or {}

    # Get current caption text
    caption = ""
    if draft.kind == "threads_series":
        posts = payload.get("threads_posts", [])
        caption = " ".join(p.get("text", "") for p in posts if p.get("text"))
    elif draft.kind == "content_series":
        posts = payload.get("series_posts", [])
        caption = " ".join(p.get("caption", "") for p in posts if p.get("caption"))
    else:
        caption = payload.get("caption", "") or payload.get("text", "")

    if not caption:
        raise HTTPException(status_code=400, detail="no_text_to_adapt")

    # Run adaptation in thread pool
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _executor, adapt_tone_sync, caption, body.tone, draft.topic, draft.kind,
    )

    # Save as revision
    try:
        from bot.services.draft_revisions_store import create_revision

        adapted_payload = dict(payload)
        adapted_payload["caption"] = result["adapted_text"]
        adapted_payload["active_tone"] = body.tone

        await create_revision(
            draft_id=draft_id,
            payload=adapted_payload,
            author=f"ai:tone:{body.tone}",
            note=f"Tone adaptation: {result['label']}",
        )
    except Exception:
        logger.warning("Failed to save tone revision for %s", draft_id, exc_info=True)

    return {
        "tone": result["tone"],
        "label": result["label"],
        "adapted_text": result["adapted_text"],
        "quality_score": result["quality_score"],
    }


@router.get("/api/drafts/{draft_id}/tone/variants", dependencies=[Depends(_require_auth)])
async def get_tone_variants(draft_id: str):
    """Get all tone variants for a draft (from revisions)."""
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")

    try:
        from bot.services.draft_revisions_store import list_revisions
        revisions = await list_revisions(draft_id)
    except Exception:
        revisions = []

    variants = {}
    for rev in revisions:
        author = rev.get("author", "") if isinstance(rev, dict) else getattr(rev, "author", "")
        if isinstance(author, str) and author.startswith("ai:tone:"):
            tone_key = author.replace("ai:tone:", "")
            rev_payload = rev.get("payload", {}) if isinstance(rev, dict) else getattr(rev, "payload", {})
            rev_num = rev.get("rev_num", 0) if isinstance(rev, dict) else getattr(rev, "rev_num", 0)
            created = rev.get("created_at", "") if isinstance(rev, dict) else getattr(rev, "created_at", "")
            variants[tone_key] = {
                "tone": tone_key,
                "rev_num": rev_num,
                "preview": (rev_payload.get("caption", "") or "")[:200],
                "created_at": str(created) if created else "",
            }

    # Include original
    payload = draft.payload or {}
    current_tone = payload.get("active_tone", "original")

    return {
        "draft_id": draft_id,
        "current_tone": current_tone,
        "variants": variants,
    }


@router.post("/api/drafts/{draft_id}/tone/apply", dependencies=[Depends(require_tier("expert"))])
async def apply_tone(draft_id: str, body: ToneApplyRequest):
    """Apply a tone variant as the current draft payload."""
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")

    if body.tone == "original":
        # Restore original by removing active_tone
        payload = draft.payload or {}
        payload.pop("active_tone", None)
        await update_draft(draft_id, payload=payload)
        return {"ok": True, "tone": "original"}

    # Find the revision for this tone
    try:
        from bot.services.draft_revisions_store import list_revisions
        revisions = await list_revisions(draft_id)
    except Exception:
        raise HTTPException(status_code=400, detail="no_revisions")

    target_rev = None
    for rev in revisions:
        author = rev.get("author", "") if isinstance(rev, dict) else getattr(rev, "author", "")
        if author == f"ai:tone:{body.tone}":
            target_rev = rev
            break

    if not target_rev:
        raise HTTPException(status_code=404, detail="tone_variant_not_found")

    rev_payload = target_rev.get("payload", {}) if isinstance(target_rev, dict) else getattr(target_rev, "payload", {})
    if rev_payload:
        await update_draft(draft_id, payload=rev_payload)

    return {"ok": True, "tone": body.tone}


@router.get("/api/tone/labels", dependencies=[Depends(_require_auth)])
async def tone_labels():
    """Get available tone labels."""
    from bot.agents.tone_adapter import get_tone_labels
    return {"tones": get_tone_labels()}
