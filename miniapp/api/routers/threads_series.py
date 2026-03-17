"""Threads Series API — slot editing, regeneration, history, approval."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from bot.services.drafts_store import get_draft, update_draft
from bot.services.miniapp_presenter import serialize_draft
from ..auth import _require_auth
from ..models import ThreadsSlotPatchRequest, ThreadsSlotRegenRequest

router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=2)

_SLOT_LABELS = {"morning": "УТРО", "day": "ДЕНЬ", "evening": "ВЕЧЕР"}
_SLOT_DESCRIPTIONS = {
    "morning": "провокационный тезис или спорное мнение + открытый вопрос (Hot Take, байт на обсуждение)",
    "day": "лаконичный список, мясной совет или быстрый туториал (для сохранений и репостов)",
    "evening": "личная история, факап, шутка или рефлексия (эмоция, уютный чат в комментариях)",
}


def _require_threads_series(draft):
    if not draft or draft.kind != "threads_series":
        raise HTTPException(status_code=404, detail="threads_series_not_found")
    return draft


@router.patch("/api/threads-series/{draft_id}/slot")
async def patch_slot(
    draft_id: str,
    payload: ThreadsSlotPatchRequest,
    _: None = Depends(_require_auth),
):
    draft = await get_draft(draft_id)
    _require_threads_series(draft)

    p = dict(draft.payload or {})
    posts = list(p.get("threads_posts", []))
    updated = False
    for post in posts:
        if post["slot"] == payload.slot:
            if payload.text is not None:
                post["text"] = payload.text
            if payload.scheduled_time is not None:
                post["scheduled_time"] = payload.scheduled_time
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=404, detail="slot_not_found")

    p["threads_posts"] = posts
    saved = await update_draft(draft_id, payload=p)
    if not saved:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(saved)


@router.post("/api/threads-series/{draft_id}/regen-slot")
async def regen_slot(
    draft_id: str,
    payload: ThreadsSlotRegenRequest,
    _: None = Depends(_require_auth),
):
    draft = await get_draft(draft_id)
    _require_threads_series(draft)

    p = dict(draft.payload or {})
    posts = list(p.get("threads_posts", []))

    slot_post = next((post for post in posts if post["slot"] == payload.slot), None)
    if not slot_post:
        raise HTTPException(status_code=404, detail="slot_not_found")

    # Save current text to versions[]
    old_text = slot_post.get("text", "")
    versions = list(slot_post.get("versions", []))
    if old_text:
        versions.append({
            "text": old_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # Regenerate via content factory (writer + editor)
    goal_key = p.get("goal", "trust")
    new_text, new_why = await _regen_slot_text(draft.topic, goal_key, payload.slot, payload.note)

    slot_post["text"] = new_text
    slot_post["why_it_works"] = new_why
    slot_post["versions"] = versions

    p["threads_posts"] = posts
    saved = await update_draft(draft_id, payload=p)
    if not saved:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(saved)


async def _regen_slot_text(topic: str, goal_key: str, slot: str, note: str | None) -> tuple[str, str]:
    loop = asyncio.get_running_loop()

    def _sync() -> tuple[str, str]:
        from bot.agents.content import _call_claude, _extract_why_it_works, BRAND_CONTEXT, GOAL_GUIDANCE
        from bot.agents.creative_team import edit_post_sync

        slot_desc = _SLOT_DESCRIPTIONS.get(slot, "один пост")
        slot_label = _SLOT_LABELS.get(slot, slot.upper())
        goal_guidance = GOAL_GUIDANCE.get(goal_key, "")
        note_block = f"\nПожелание: {note}\n" if note else ""

        prompt = f"""{BRAND_CONTEXT}
Роль: ты топовый контент-стратег и автор в Threads с навыками вирального сторителлинга.
Напиши один пост для серии Threads.

Тема серии: {topic}
Цель: {goal_guidance}
Слот: {slot_label} — {slot_desc}.
{note_block}
Стиль:
- Первая строчка = 80% успеха. Провокационная или очень жизненная.
- Короткие, рубленые предложения. Минимум эмодзи (1-2 на пост).
- Никаких ИИ-штампов: забудь слова «трансформация», «ключевой», «инсайт», «в современном мире».

Правила:
- Один пост, одна идея, 5-12 коротких строк, 40-120 слов
- Разговорный стиль, без хэштегов, без длинных вводных
- Звучит как живой человек, не как лектор

В конце добавь строку: ПОЧЕМУ ЭТО СРАБОТАЕТ: [одно предложение]
Верни только текст поста, без меток УТРО/ДЕНЬ/ВЕЧЕР.
"""
        raw = _call_claude(prompt, max_tokens=400)
        edited = edit_post_sync(raw, topic, platform="threads_slot")
        text, why = _extract_why_it_works(edited)
        return text, why

    return await loop.run_in_executor(_executor, _sync)


@router.get("/api/threads-series/{draft_id}/slot-history/{slot}")
async def slot_history(
    draft_id: str,
    slot: str,
    _: None = Depends(_require_auth),
):
    draft = await get_draft(draft_id)
    _require_threads_series(draft)

    posts = (draft.payload or {}).get("threads_posts", [])
    slot_post = next((p for p in posts if p["slot"] == slot), None)
    if not slot_post:
        raise HTTPException(status_code=404, detail="slot_not_found")

    return {"slot": slot, "versions": slot_post.get("versions", [])}


@router.post("/api/threads-series/{draft_id}/approve")
async def approve_series(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    _require_threads_series(draft)

    saved = await update_draft(draft_id, status="approved")
    if not saved:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(saved)
