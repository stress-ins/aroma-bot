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
    from bot.services.miniapp_references import build_reference_context, list_reference_cards
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
    return {"recommendations": enriched, "general_advice": result.get("general_advice", "")}
