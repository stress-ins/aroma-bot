from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from telegram import Bot

from bot.services.drafts_store import delete_draft, get_draft, list_recent_drafts, update_draft
from bot.services.draft_revisions_store import create_revision, get_revision, list_revisions
from bot.services.miniapp_content_review import polish_content_review_draft, update_content_review_draft
from bot.services.miniapp_presenter import filter_drafts, serialize_draft, serialize_draft_summary
from config import settings
from ..auth import _require_auth
from ..models import DraftContentPayload, DraftFeedbackPayload, DraftStatusPayload

router = APIRouter()


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


@router.get("/api/drafts")
async def drafts(
    limit: int = Query(default=50, ge=1, le=200),
    kind: str = "",
    status: str = "",
    feedback: str = "",
    query: str = "",
    _: None = Depends(_require_auth),
):
    records = await list_recent_drafts(limit=200, newest_first=True)
    filtered = await filter_drafts(records, kind=kind, status=status, feedback=feedback, query=query)
    return {"items": [await serialize_draft_summary(record) for record in filtered[:limit]], "total": len(filtered)}


@router.get("/api/drafts/{draft_id}")
async def draft_detail(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(draft)


@router.post("/api/drafts/{draft_id}/status")
async def update_status(draft_id: str, payload: DraftStatusPayload, _: None = Depends(_require_auth)):
    status = payload.status.strip().lower()
    if status not in {"draft", "in_review", "approved", "published", "rejected"}:
        raise HTTPException(status_code=400, detail="invalid_status")
    draft = await update_draft(draft_id, status=status)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(draft)


@router.delete("/api/drafts/{draft_id}")
async def remove_draft(draft_id: str, _: None = Depends(_require_auth)):
    deleted = await delete_draft(draft_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return {"ok": True, "draft_id": draft_id}


@router.post("/api/drafts/{draft_id}/feedback")
async def update_feedback(draft_id: str, payload: DraftFeedbackPayload, _: None = Depends(_require_auth)):
    feedback = payload.feedback.strip().lower()
    if feedback not in {"", "worked", "missed"}:
        raise HTTPException(status_code=400, detail="invalid_feedback")
    draft = await update_draft(draft_id, feedback=feedback)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(draft)


@router.post("/api/drafts/{draft_id}/content")
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
        threads_posts=payload.threads_posts,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="content_draft_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    await create_revision(draft_id, draft.payload, author="user", note="manual save")
    return await serialize_draft(draft)


@router.post("/api/drafts/{draft_id}/content/polish")
async def polish_content(draft_id: str, _: None = Depends(_require_auth)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="anthropic_not_configured")
    updated = await polish_content_review_draft(draft_id)
    if not updated:
        raise HTTPException(status_code=404, detail="content_draft_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    await create_revision(draft_id, draft.payload, author="ai:polish", note="AI polish")
    return await serialize_draft(draft)


@router.get("/api/drafts/{draft_id}/revisions")
async def list_draft_revisions(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    revisions = await list_revisions(draft_id)
    return {"items": [r.to_dict() for r in revisions]}


@router.get("/api/drafts/{draft_id}/revisions/{rev_num}")
async def get_draft_revision(draft_id: str, rev_num: int, _: None = Depends(_require_auth)):
    revision = await get_revision(draft_id, rev_num)
    if not revision:
        raise HTTPException(status_code=404, detail="revision_not_found")
    return revision.to_dict()


@router.post("/api/drafts/{draft_id}/revisions/{rev_num}/restore")
async def restore_draft_revision(draft_id: str, rev_num: int, _: None = Depends(_require_auth)):
    revision = await get_revision(draft_id, rev_num)
    if not revision:
        raise HTTPException(status_code=404, detail="revision_not_found")
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    # Snapshot current before restoring
    await create_revision(draft_id, draft.payload, author="system", note=f"snapshot before restore to rev {rev_num}")
    updated = await update_draft(draft_id, payload=revision.payload)
    if not updated:
        raise HTTPException(status_code=404, detail="draft_not_found")
    await create_revision(draft_id, revision.payload, author="system", note=f"restored from rev {rev_num}")
    return await serialize_draft(updated)


@router.post("/api/drafts/{draft_id}/send")
async def send_draft_to_chat(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if not settings.telegram_bot_token or not settings.report_target_chat_id:
        raise HTTPException(status_code=400, detail="telegram_not_configured")
    bot = Bot(token=settings.telegram_bot_token)
    await bot.send_message(chat_id=settings.report_target_chat_id, text=_draft_chat_message(draft))
    return {"ok": True}
