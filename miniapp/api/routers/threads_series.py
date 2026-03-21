"""Threads Series API — slot editing, regeneration, history, approval."""
from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from bot.services.drafts_store import get_draft, update_draft
from bot.services.miniapp_presenter import serialize_draft
from ..auth import _require_auth
from ..models import ThreadsSlotPatchRequest, ThreadsSlotRegenRequest

logger = logging.getLogger(__name__)

router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=2)

_SLOT_LABELS = {"morning": "УТРО", "day": "ДЕНЬ", "evening": "ВЕЧЕР"}

_ANALYSIS_RE = re.compile(
    r"(?:"
    r"Отличный пост|Хороший пост|Неплохой пост|Сильный пример"
    r"|Что работает[:\s]"
    r"|Что правда[:\s]"
    r"|Что не работает[:\s]"
    r"|Почему хвалят[:\s]"
    r"|Честнее было бы"
    r"|но разберу"
    r"|Замечани[яе][:\s]"
    r"|Анализ[:\s]"
    r"|Рекомендаци[ия][:\s]"
    r"|Разбор[:\s]"
    r"|Оценка[:\s]"
    r"|✅\s*Что"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

_THREADS_MAX_CHARS = 500


def _force_shorten(text: str, topic: str, max_chars: int = _THREADS_MAX_CHARS) -> str:
    """If text still exceeds max_chars after trimming, rewrite it shorter via LLM."""
    if len(text) <= max_chars:
        return text
    import bot.agents.content as _content_mod
    prompt = (
        f"Перепиши этот пост для Threads СТРОГО короче {max_chars} символов. "
        f"Сейчас {len(text)} символов — нужно убрать {len(text) - max_chars}. "
        f"Сохрани первую строку (хук) и основную мысль. Убери лишние детали и длинные фразы. "
        f"Тема: {topic}\n\nТекст:\n{text}\n\n"
        f"Верни ТОЛЬКО сокращённый текст поста, ничего больше."
    )
    result = _content_mod._call_claude(prompt, max_tokens=300)
    shortened = result.strip()
    # Use shortened only if it's actually shorter and non-trivial
    if len(shortened) < len(text) and len(shortened) > 20:
        return shortened
    return text
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
- Один пост, одна идея, 5-10 коротких строк, 40-80 слов
- НЕ БОЛЬШЕ 80 СЛОВ. Пост, превышающий 80 слов, считается провалом задания. Максимум 500 символов.
- Разговорный стиль, без хэштегов, без длинных вводных
- Звучит как живой человек, не как лектор

В конце добавь строку: ПОЧЕМУ ЭТО СРАБОТАЕТ: [одно предложение]
Верни только текст поста, без меток УТРО/ДЕНЬ/ВЕЧЕР.

ЗАПРЕЩЕНО:
- Возвращать разбор, анализ, комментарии или объяснения вместо поста.
- Использовать markdown: # заголовки, **жирный**, > цитаты, нумерованные списки.
- Писать что-либо кроме готового текста поста + строки ПОЧЕМУ ЭТО СРАБОТАЕТ.
- НЕ включай в текст метки формата в скобках, такие как (Hot Take), (Thread), (Байт на обсуждение), (Список), (Туториал), (Рефлексия), (Шутка), (Факап), (Личная история).
"""
        raw = _call_claude(prompt, max_tokens=400)
        edited = edit_post_sync(raw, topic, platform="threads_slot")

        # Guard: if editor returned analysis/review instead of a post, fall back to raw
        if _ANALYSIS_RE.search(edited.strip()):
            logger.warning("Editor returned analysis instead of post, using raw writer output")
            edited = raw

        # Strip any markdown formatting that slipped through
        from bot.agents.content import _strip_markdown_formatting
        edited = _strip_markdown_formatting(edited)
        text, why = _extract_why_it_works(edited)
        from bot.agents.content import _strip_format_labels
        text = _strip_format_labels(text)

        # Guard: trim if text exceeds limits
        if len(text) > _THREADS_MAX_CHARS or len(text.split()) > 120:
            from bot.agents.content import _trim_thread_post_sync
            text = _trim_thread_post_sync(text, topic)

        # Last resort: rewrite shorter via LLM
        if len(text) > _THREADS_MAX_CHARS:
            text = _force_shorten(text, topic)

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


@router.post("/api/threads-series/{draft_id}/regenerate-posts")
async def regenerate_posts(draft_id: str, _: None = Depends(_require_auth)):
    """Regenerate all posts for a threads_series with empty threads_posts."""
    draft = await get_draft(draft_id)
    _require_threads_series(draft)

    from bot.services.miniapp_generator import build_threads_series_payload
    from bot.agents import generate_content_draft

    p = dict(draft.payload or {})
    goal_key = p.get("goal", "trust")
    emotion = p.get("emotion", "")

    raw_draft = await generate_content_draft(draft.topic, goal_key, "threads_series")
    new_payload = build_threads_series_payload(raw_draft, goal_key=goal_key, emotion=emotion)

    # Preserve existing series_summary if the new one is empty
    if p.get("series_summary") and not new_payload.get("series_summary"):
        new_payload["series_summary"] = p["series_summary"]

    new_posts = new_payload.get("threads_posts", [])
    if not any(p.get("text") for p in new_posts):
        raise HTTPException(status_code=502, detail="generation_produced_no_posts")

    saved = await update_draft(draft_id, payload=new_payload)
    if not saved:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(saved)


@router.post("/api/threads-series/{draft_id}/approve")
async def approve_series(draft_id: str, _: None = Depends(_require_auth)):
    draft = await get_draft(draft_id)
    _require_threads_series(draft)

    posts = (draft.payload or {}).get("threads_posts", [])
    if not posts:
        raise HTTPException(status_code=400, detail="no_posts_to_approve")

    saved = await update_draft(draft_id, status="approved")
    if not saved:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return await serialize_draft(saved)


@router.post("/api/threads-series/{draft_id}/slots/{slot}/publish-now")
async def publish_slot_now(
    draft_id: str, slot: str, _: None = Depends(_require_auth),
):
    """Publish a single slot of a threads_series immediately."""
    from bot.services.publisher import publish_threads_series_slot

    draft = await get_draft(draft_id)
    _require_threads_series(draft)
    if draft.status not in ("approved", "scheduled"):
        raise HTTPException(
            status_code=400, detail="draft_must_be_approved_or_scheduled",
        )

    posts = (draft.payload or {}).get("threads_posts", [])
    slot_post = next((p for p in posts if p["slot"] == slot), None)
    if not slot_post:
        raise HTTPException(status_code=404, detail="slot_not_found")
    if slot_post.get("status") == "published":
        return {"draft_id": draft_id, "slot": slot, "status": "already_published"}

    result = await publish_threads_series_slot(draft_id, slot)
    return {"draft_id": draft_id, "slot": slot, "status": "ok", "result": result}


@router.post("/api/threads-series/{draft_id}/publish-now")
async def publish_series_now(draft_id: str, _: None = Depends(_require_auth)):
    """Publish ALL posts of a threads_series immediately with 30s pauses."""
    from bot.services.publisher import publish_threads_series_slot

    draft = await get_draft(draft_id)
    _require_threads_series(draft)
    if draft.status not in ("approved", "scheduled"):
        raise HTTPException(
            status_code=400, detail="draft_must_be_approved_or_scheduled",
        )

    posts = (draft.payload or {}).get("threads_posts", [])
    if not posts:
        raise HTTPException(status_code=400, detail="no_posts_to_publish")

    results = []
    for i, post in enumerate(posts):
        if post.get("status") == "published":
            results.append({"slot": post["slot"], "status": "already_published"})
            continue
        try:
            result = await publish_threads_series_slot(draft_id, post["slot"])
            results.append(result)
            logger.info(
                "publish-now: slot %s published for %s", post["slot"], draft_id,
            )
        except Exception as exc:
            logger.error(
                "publish-now: slot %s failed for %s: %s",
                post["slot"], draft_id, exc,
            )
            results.append({
                "slot": post["slot"], "status": "error", "error": str(exc),
            })
        # Pause between posts (except after the last one)
        if i < len(posts) - 1:
            await asyncio.sleep(30)

    # Notify admin about failed slots
    error_slots = [r for r in results if r.get("status") == "error"]
    if error_slots:
        from bot.handlers.monitor import notify_owner
        await notify_owner(
            f"⚠️ Publish-now failed for {draft_id}:\n"
            + "\n".join(f"  {r['slot']}: {r['error']}" for r in error_slots)
        )

    updated = await get_draft(draft_id)
    return {
        "draft_id": draft_id,
        "status": updated.status if updated else "unknown",
        "results": results,
    }
