from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from telegram import Bot

from bot.services.drafts_store import delete_draft, get_draft, list_recent_drafts, update_draft
from bot.services.draft_revisions_store import create_revision, get_revision, list_revisions
from bot.services.miniapp_content_review import polish_content_review_draft, update_content_review_draft
from bot.services.miniapp_presenter import filter_drafts, serialize_draft, serialize_draft_summary
from bot.services.post_metrics_store import get_latest_metrics_batch
from config import settings
from ..auth import TeamContext, _require_auth, _resolve_team_context, _telegram_user_id_from_init_data
from ..models import DraftContentPayload, DraftFeedbackPayload, DraftMovePayload, DraftStatusPayload

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
    if draft.kind == "reels_v2":
        concept = str(payload.get("concept") or "").strip()[:200]
        video_status = str(payload.get("video_status") or "none")
        bot_user = settings.telegram_bot_username
        deep_link = f"https://t.me/{bot_user}?start=upload_{draft.draft_id}"
        lines = [f"🎬 Рилс\n\nТема: {draft.topic}"]
        if concept:
            lines.append(f"\n{concept}")
        if video_status in ("none", "uploaded"):
            lines.append(
                f"\n📎 Чтобы загрузить видео, отправьте файл прямо в этот чат "
                f"или перейдите по ссылке:\n{deep_link}"
            )
        return "\n".join(lines).strip()
    text = str(payload.get("caption") or payload.get("hook") or payload.get("angle") or "").strip()
    return f"{draft.kind.title()}\n\nТема: {draft.topic}\n\n{text}".strip()


@router.get("/api/drafts")
async def drafts(
    limit: int = Query(default=50, ge=1, le=200),
    kind: str = "",
    status: str = "",
    feedback: str = "",
    query: str = "",
    include_metrics: bool = Query(default=False),
    ctx: TeamContext = Depends(_resolve_team_context),
):
    records = await list_recent_drafts(
        limit=limit, newest_first=True, team_id=ctx.team_id,
        kind=kind or None, status=status or None, feedback=feedback or None,
    )
    filtered = await filter_drafts(records, query=query)
    items = [await serialize_draft_summary(record) for record in filtered[:limit]]

    if include_metrics:
        published_ids = [it["draft_id"] for it in items if it.get("status") == "published"]
        if published_ids:
            metrics_batch = await get_latest_metrics_batch(published_ids)
            for it in items:
                if it["draft_id"] in metrics_batch:
                    it["metrics_summary"] = metrics_batch[it["draft_id"]]

    return {"items": items, "total": len(filtered)}


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


@router.post("/api/drafts/{draft_id}/move")
async def move_draft(draft_id: str, payload: DraftMovePayload, ctx: TeamContext = Depends(_resolve_team_context)):
    from bot.services.team_store import get_member_role, has_role

    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")

    target_role = await get_member_role(payload.target_team_id, ctx.telegram_id)
    if not target_role or not has_role(target_role, "editor"):
        raise HTTPException(status_code=403, detail="insufficient_role_in_target_team")

    updated = await update_draft(draft_id, team_id=payload.target_team_id)
    if not updated:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(updated)


@router.post("/api/drafts/{draft_id}/send")
async def send_draft_to_chat(
    draft_id: str,
    _: None = Depends(_require_auth),
    x_telegram_init_data: str | None = Header(default=None),
):
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if not settings.telegram_bot_token or not settings.report_target_chat_id:
        raise HTTPException(status_code=400, detail="telegram_not_configured")
    bot = Bot(token=settings.telegram_bot_token)
    # Try to send to the requesting user's personal chat; fall back to admin
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data or "") if x_telegram_init_data else None
    chat_id = str(user_id) if user_id else settings.report_target_chat_id
    await bot.send_message(chat_id=chat_id, text=_draft_chat_message(draft))
    return {"ok": True}
