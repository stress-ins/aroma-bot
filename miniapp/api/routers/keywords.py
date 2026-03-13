from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from bot.services.miniapp_keywords import add_keyword, delete_keyword, field_labels, serialize_topics
from ..auth import _require_auth
from ..models import KeywordPayload

router = APIRouter()


@router.get("/api/keywords")
async def keywords(_: None = Depends(_require_auth)):
    return {"items": serialize_topics(), "field_labels": field_labels()}


@router.post("/api/keywords/add")
async def keyword_add(payload: KeywordPayload, _: None = Depends(_require_auth)):
    word = payload.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="empty_word")
    add_keyword(payload.topic_idx, payload.field, word)
    return {"ok": True, "items": serialize_topics(), "field_labels": field_labels()}


@router.post("/api/keywords/remove")
async def keyword_remove(payload: KeywordPayload, _: None = Depends(_require_auth)):
    word = payload.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="empty_word")
    delete_keyword(payload.topic_idx, payload.field, word)
    return {"ok": True, "items": serialize_topics(), "field_labels": field_labels()}
