"""Personal oil recommendations endpoint."""
from __future__ import annotations
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from miniapp.api.auth import _resolve_telegram_id
router = APIRouter()
class PersonalRecommendationRequest(BaseModel):
    mood: str; goal: str; symptoms: list[str] = []; aroma_preferences: list[str] = []; contraindications: str = ""
@router.post("/api/recommendations/personal")
async def personal_recommendations(body: PersonalRecommendationRequest, telegram_id: int = Depends(_resolve_telegram_id)):
    if not body.mood.strip() or not body.goal.strip(): raise HTTPException(status_code=400, detail="mood and goal are required")
    from bot.agents.recommendation_agent import recommend_oils_sync
    from bot.services.llm_cache import get_cached, make_cache_key, set_cached
    from bot.services.miniapp_references import build_reference_context, list_reference_cards

    # Check cache
    symptoms_str = ",".join(sorted(body.symptoms)) if body.symptoms else ""
    aroma_str = ",".join(sorted(body.aroma_preferences)) if body.aroma_preferences else ""
    cache_key = make_cache_key("reco", mood=body.mood, goal=body.goal, symptoms=symptoms_str, aroma_preferences=aroma_str, contraindications=body.contraindications.strip().lower())
    scope_tid = telegram_id if body.symptoms else None
    cached = await get_cached(cache_key)
    if cached:
        return cached

    reference_context = await build_reference_context(categories=("aroma",), max_items_per_category=30, max_total_chars=3000)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, recommend_oils_sync, body.mood, body.goal, body.symptoms, body.aroma_preferences, body.contraindications, reference_context)
    recommendations = result.get("recommendations", [])
    aromas = await list_reference_cards("aroma")
    aroma_map = {}
    for a in aromas:
        for key in ((a.get("slug") or "").lower(), (a.get("name") or "").lower(), (a.get("name_en") or "").lower()):
            if key: aroma_map[key] = a
    enriched = []
    for rec in recommendations[:3]:
        card = aroma_map.get((rec.get("slug") or "").lower()) or aroma_map.get((rec.get("name_ru") or "").lower())
        enriched.append({"slug": rec.get("slug", ""), "name_ru": rec.get("name_ru", ""), "reason": rec.get("reason", ""), "daily_practice": rec.get("daily_practice", ""), "card": card})
    response = {"recommendations": enriched, "general_advice": result.get("general_advice", "")}
    await set_cached(cache_key, "recommendation", response, ttl_hours=24, telegram_id=scope_tid)
    return response


class MassageRecommendationRequest(BaseModel):
    concern: str
    body_zone: str
    goal: str
    experience: str = "some"
    contraindications: str = ""


@router.post("/api/recommendations/massage")
async def massage_recommendations(body: MassageRecommendationRequest, telegram_id: int = Depends(_resolve_telegram_id)):
    if not body.concern.strip() or not body.body_zone.strip():
        raise HTTPException(status_code=400, detail="concern and body_zone are required")
    from bot.agents.massage_recommendation_agent import recommend_massage_sync
    from bot.services.llm_cache import get_cached, make_cache_key, set_cached
    from bot.services.miniapp_references import build_reference_context, list_reference_cards

    cache_key = make_cache_key("reco_massage", concern=body.concern, body_zone=body.body_zone, goal=body.goal, experience=body.experience, contraindications=body.contraindications.strip().lower())
    cached = await get_cached(cache_key)
    if cached:
        return cached

    reference_context = await build_reference_context(categories=("massage",), max_items_per_category=20, max_total_chars=4000)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, recommend_massage_sync, body.concern, body.body_zone, body.goal, body.experience, body.contraindications, reference_context)
    recommendations = result.get("recommendations", [])
    massage_cards = await list_reference_cards("massage")
    card_map = {}
    for c in massage_cards:
        for key in ((c.get("slug") or "").lower(), (c.get("name") or "").lower(), (c.get("name_en") or "").lower()):
            if key:
                card_map[key] = c
    enriched = []
    for rec in recommendations[:3]:
        card = card_map.get((rec.get("slug") or "").lower()) or card_map.get((rec.get("name_ru") or "").lower())
        enriched.append({
            "slug": rec.get("slug", ""),
            "name_ru": rec.get("name_ru", ""),
            "reason": rec.get("reason", ""),
            "session_advice": rec.get("session_advice", ""),
            "oils": rec.get("oils", []),
            "card": card,
        })
    response = {"recommendations": enriched, "general_advice": result.get("general_advice", "")}
    await set_cached(cache_key, "recommendation_massage", response, ttl_hours=24, telegram_id=telegram_id)
    return response


class ProtocolRecommendationRequest(BaseModel):
    concern: str
    body_zone: str = "full_body"
    goal: str = "balance"
    modalities: str = "all"
    contraindications: str = ""


@router.post("/api/recommendations/protocol")
async def protocol_recommendations(body: ProtocolRecommendationRequest, telegram_id: int = Depends(_resolve_telegram_id)):
    if not body.concern.strip():
        raise HTTPException(status_code=400, detail="concern is required")
    from bot.agents.protocol_recommendation_agent import recommend_protocol_sync
    from bot.services.llm_cache import get_cached, make_cache_key, set_cached
    from bot.services.miniapp_references import build_reference_context, list_reference_cards

    cache_key = make_cache_key(
        "reco_protocol", concern=body.concern, body_zone=body.body_zone,
        goal=body.goal, modalities=body.modalities,
        contraindications=body.contraindications.strip().lower(),
    )
    cached = await get_cached(cache_key)
    if cached:
        return cached

    reference_context = await build_reference_context(
        categories=("aroma", "massage", "sound", "crystal"),
        max_items_per_category=15,
        max_total_chars=6000,
    )
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, recommend_protocol_sync,
        body.concern, body.body_zone, body.goal, body.modalities,
        body.contraindications, reference_context,
    )

    # Enrich each modality with full card data
    card_maps = {}
    for cat in ("aroma", "massage", "sound", "crystal"):
        cards = await list_reference_cards(cat)
        cmap = {}
        for c in cards:
            for key in ((c.get("slug") or "").lower(), (c.get("name") or "").lower()):
                if key:
                    cmap[key] = c
        card_maps[cat] = cmap

    for modality in ("oil", "massage", "sound", "crystal"):
        rec = result.get(modality)
        if not rec or not isinstance(rec, dict):
            continue
        cat = "aroma" if modality == "oil" else modality
        slug = (rec.get("slug") or "").lower()
        card = card_maps.get(cat, {}).get(slug)
        rec["card"] = card

    response = {
        "protocol_name": result.get("protocol_name", ""),
        "protocol_description": result.get("protocol_description", ""),
        "oil": result.get("oil"),
        "massage": result.get("massage"),
        "sound": result.get("sound"),
        "crystal": result.get("crystal"),
        "session_plan": result.get("session_plan", []),
        "synergy": result.get("synergy", ""),
        "total_duration_min": result.get("total_duration_min", 0),
        "general_advice": result.get("general_advice", ""),
    }
    await set_cached(cache_key, "recommendation_protocol", response, ttl_hours=24, telegram_id=telegram_id)
    return response
