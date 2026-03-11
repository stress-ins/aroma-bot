from __future__ import annotations

from bot.agents.creative_team import edit_post_sync
from bot.services.drafts_store import get_draft, update_draft


EDITABLE_KINDS = {"threads", "instagram", "telegram"}
EDITABLE_FIELDS = ("angle", "hook", "caption", "cta", "hashtags", "visual_prompt")


def is_content_review_draft(kind: str) -> bool:
    return kind.strip().lower() in EDITABLE_KINDS


def update_content_review_draft(
    draft_id: str,
    *,
    topic: str,
    angle: str,
    hook: str,
    caption: str,
    cta: str,
    hashtags: str,
    visual_prompt: str,
) -> dict[str, object] | None:
    draft = get_draft(draft_id)
    if not draft or not is_content_review_draft(draft.kind):
        return None

    payload = dict(draft.payload)
    payload["angle"] = angle.strip()
    payload["hook"] = hook.strip()
    payload["caption"] = caption.strip()
    payload["cta"] = cta.strip()
    payload["hashtags"] = hashtags.strip()
    payload["visual_prompt"] = visual_prompt.strip()

    updated = update_draft(
        draft_id,
        topic=topic.strip() or draft.topic,
        payload=payload,
        status="draft",
    )
    return payload if updated else None


def polish_content_review_draft(draft_id: str) -> dict[str, object] | None:
    draft = get_draft(draft_id)
    if not draft or not is_content_review_draft(draft.kind):
        return None

    payload = dict(draft.payload)
    raw_text = str(payload.get("caption", "")).strip()
    if not raw_text:
        raw_text = str(payload.get("hook", "")).strip()
    if not raw_text:
        return None

    polished = edit_post_sync(raw_text, draft.topic, platform=draft.kind)
    if str(payload.get("caption", "")).strip():
        payload["caption"] = polished.strip()
    else:
        payload["hook"] = polished.strip()

    updated = update_draft(draft_id, payload=payload, status="draft")
    return payload if updated else None
