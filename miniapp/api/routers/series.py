"""Content Series API router."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path

from bot.services.drafts_store import get_draft, update_draft
from bot.services.miniapp_presenter import serialize_draft

from ..auth import TeamContext, _resolve_team_context, require_tier
from ..deps import verify_team_draft
from ..models import SeriesPostPatchRequest, SeriesRegenPostRequest

logger = logging.getLogger(__name__)
router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)


def _require_content_series(draft):
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if draft.kind != "content_series":
        raise HTTPException(status_code=400, detail="not_content_series")
    return draft


@router.get("/api/series/{draft_id}")
async def get_series(draft_id: str, ctx: TeamContext = Depends(_resolve_team_context)):
    """Get content series details."""
    draft = await get_draft(draft_id)
    _require_content_series(draft)
    verify_team_draft(draft, ctx)
    return await serialize_draft(draft)


@router.patch("/api/series/{draft_id}/post/{index}", dependencies=[Depends(require_tier("expert"))])
async def patch_series_post(
    draft_id: str,
    ctx: TeamContext = Depends(_resolve_team_context),
    index: int = Path(..., ge=0, le=6),
    body: SeriesPostPatchRequest = ...,
):
    """Edit a single post in the series."""
    draft = await get_draft(draft_id)
    _require_content_series(draft)
    verify_team_draft(draft, ctx)

    payload = draft.payload or {}
    posts = payload.get("series_posts", [])
    if index >= len(posts):
        raise HTTPException(status_code=400, detail="invalid_post_index")

    post = posts[index]

    # Save current version before editing
    if post.get("caption") and body.caption is not None:
        versions = post.get("versions", [])
        from datetime import datetime, timezone
        versions.append({"text": post["caption"], "created_at": datetime.now(timezone.utc).isoformat()})
        post["versions"] = versions[-10:]  # Keep last 10

    if body.caption is not None:
        post["caption"] = body.caption
    if body.cta is not None:
        post["cta"] = body.cta
    if body.visual_prompt is not None:
        post["visual_prompt"] = body.visual_prompt
    if body.hashtags is not None:
        post["hashtags"] = body.hashtags
    if body.scheduled_at is not None:
        post["scheduled_at"] = body.scheduled_at

    posts[index] = post
    payload["series_posts"] = posts
    await update_draft(draft_id, payload=payload)
    updated = await get_draft(draft_id)
    return await serialize_draft(updated)


@router.post("/api/series/{draft_id}/regen-post/{index}", dependencies=[Depends(require_tier("expert"))])
async def regen_series_post(
    draft_id: str,
    ctx: TeamContext = Depends(_resolve_team_context),
    index: int = Path(..., ge=0, le=6),
    body: SeriesRegenPostRequest = SeriesRegenPostRequest(),
):
    """Regenerate a single post in the series."""
    draft = await get_draft(draft_id)
    _require_content_series(draft)
    verify_team_draft(draft, ctx)

    payload = draft.payload or {}
    posts = payload.get("series_posts", [])
    if index >= len(posts):
        raise HTTPException(status_code=400, detail="invalid_post_index")

    post = posts[index]
    old_caption = post.get("caption", "")

    # Save version
    if old_caption:
        versions = post.get("versions", [])
        from datetime import datetime, timezone
        versions.append({"text": old_caption, "created_at": datetime.now(timezone.utc).isoformat()})
        post["versions"] = versions[-10:]

    # Regenerate via Claude
    loop = asyncio.get_running_loop()
    new_text = await loop.run_in_executor(
        _executor,
        _regen_single_post,
        draft.topic,
        payload.get("goal_key", "trust"),
        payload.get("format_key", "instagram"),
        post,
        payload.get("outline", {}),
        posts,
        body.note,
    )

    post["caption"] = new_text
    posts[index] = post
    payload["series_posts"] = posts
    await update_draft(draft_id, payload=payload)
    updated = await get_draft(draft_id)
    return await serialize_draft(updated)


def _regen_single_post(
    topic: str,
    goal_key: str,
    format_key: str,
    post: dict,
    outline: dict,
    all_posts: list[dict],
    note: str | None,
) -> str:
    """Regenerate a single series post (sync, runs in executor)."""
    from bot.agents.prompts.series_prompts import writer_batch_prompt
    from bot.agents.series_writer import summarize_posts
    from bot.services.claude_client import call_claude
    from bot.services.humanizer import humanize

    from miniapp.api.generation.series import GOAL_GUIDANCE, _format_outline

    outline_text = _format_outline(outline)
    prev_summaries = summarize_posts([p for p in all_posts if p["index"] != post["index"]])

    position = {
        "index": post["index"],
        "title": post.get("title", f"Пост {post['index'] + 1}"),
        "role": post.get("role", "middle"),
    }

    note_block = ""
    if note:
        note_block = f"\n\nПожелание к этому посту: {note}"

    prompt = writer_batch_prompt(
        topic, goal_key, format_key, outline_text,
        [position], prev_summaries, GOAL_GUIDANCE,
    ) + note_block

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        context="series_regen_post",
    )

    # Extract caption from response
    caption = ""
    for line in raw.strip().splitlines():
        cleaned = line.strip().replace("**", "")
        if cleaned.upper().startswith("CAPTION:"):
            caption = humanize(cleaned.split(":", 1)[1].strip())
        elif caption and not cleaned.upper().startswith(("CTA:", "VISUAL_PROMPT:", "HASHTAGS:", "===POST")):
            if cleaned:
                caption += "\n" + humanize(cleaned)

    return caption or humanize(raw.strip()[:500])


@router.post("/api/series/{draft_id}/regen-all", dependencies=[Depends(require_tier("expert"))])
async def regen_all_posts(
    draft_id: str,
    background_tasks: BackgroundTasks,
    ctx: TeamContext = Depends(_resolve_team_context),
):
    """Regenerate all posts in the series."""
    from ..generation import complete_series_generation

    draft = await get_draft(draft_id)
    _require_content_series(draft)
    verify_team_draft(draft, ctx)

    payload = draft.payload or {}

    # Reset to generating state
    payload["generation_pending"] = True
    payload["generation_stage"] = "outline"
    payload["generation_message"] = "Перегенерирую серию..."
    payload["series_posts"] = []
    await update_draft(draft_id, payload=payload)

    background_tasks.add_task(
        complete_series_generation,
        draft_id, draft.topic,
        payload.get("goal_key", "trust"),
        payload.get("format_key", "instagram"),
        payload.get("post_count", 5),
        payload.get("template_key", "custom"),
    )
    updated = await get_draft(draft_id)
    return await serialize_draft(updated)


@router.post("/api/series/{draft_id}/coherence-check", dependencies=[Depends(require_tier("expert"))])
async def coherence_check(draft_id: str, ctx: TeamContext = Depends(_resolve_team_context)):
    """Run coherence check on the series."""
    from bot.agents.series_coherence import check_coherence_sync

    draft = await get_draft(draft_id)
    _require_content_series(draft)
    verify_team_draft(draft, ctx)

    payload = draft.payload or {}
    posts = payload.get("series_posts", [])
    if not posts:
        raise HTTPException(status_code=400, detail="no_posts")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _executor, check_coherence_sync, draft.topic, posts,
    )

    payload["coherence_score"] = result["score"]
    payload["coherence_issues"] = result["issues"]
    payload["coherence_suggestion"] = result.get("suggestion", "")
    await update_draft(draft_id, payload=payload)

    return result


@router.post("/api/series/{draft_id}/approve", dependencies=[Depends(require_tier("expert"))])
async def approve_series(draft_id: str, ctx: TeamContext = Depends(_resolve_team_context)):
    """Approve the entire series."""
    draft = await get_draft(draft_id)
    _require_content_series(draft)
    verify_team_draft(draft, ctx)

    await update_draft(draft_id, status="approved")
    updated = await get_draft(draft_id)
    return await serialize_draft(updated)


@router.get("/api/series/templates", dependencies=[Depends(_resolve_team_context)])
async def list_templates():
    """List available series templates."""
    from miniapp.api.generation.series import get_series_templates
    return {"templates": get_series_templates()}
