"""Recommendation agent — personal oil recommendations based on user preferences."""
from __future__ import annotations
import json, logging
logger = logging.getLogger(__name__)
_SYSTEM_PROMPT = "Ты — эксперт по ароматерапии. ВСЕГДА отвечай ТОЛЬКО на русском языке, даже если справочник содержит английский текст. На основе предпочтений пользователя подбери 3 эфирных масла из предоставленного справочника. Для каждого масла укажи: slug (из справочника), причину выбора (2-3 предложения) и практику применения на день.\n\nПравила для daily_practice:\n- Не упоминай «аромалампу» — используй «диффузор»\n- Вместо «нюхать из флакона» — «капните на ладонь и вдыхайте»\n- Ванна: «предварительно накапайте на соль или в жирные сливки»"
_USER_PROMPT = "Отвечай строго на русском языке.\n\nНастроение: {mood}\nЦель: {goal}\nСимптомы: {symptoms}\nПредпочтения по аромату: {aroma_preferences}\nПротивопоказания: {contraindications}\n\nСправочник масел:\n{reference_context}\n\nВерни строго JSON:\n{{\n  \"recommendations\": [\n    {{\"slug\": \"lavender\", \"name_ru\": \"Лаванда\", \"reason\": \"...\", \"daily_practice\": \"...\"}},\n    ...\n  ],\n  \"general_advice\": \"...\"\n}}"
_MOOD = {"stressed": "стресс", "tired": "усталость", "anxious": "тревога", "neutral": "нормально", "energetic": "энергия"}
_GOAL = {"relax": "расслабиться", "focus": "сфокусироваться", "sleep": "уснуть", "energy": "энергия", "mood": "настроение"}
def recommend_oils_sync(mood: str, goal: str, symptoms: list[str], aroma_preferences: list[str], contraindications: str, reference_context: str) -> dict:
    from bot.services.claude_client import HAIKU, call_claude
    prompt = _USER_PROMPT.format(mood=_MOOD.get(mood, mood), goal=_GOAL.get(goal, goal), symptoms=", ".join(symptoms) if symptoms else "не указаны", aroma_preferences=", ".join(aroma_preferences) if aroma_preferences else "не указаны", contraindications=contraindications or "нет", reference_context=reference_context[:3000])
    raw = call_claude(messages=[{"role": "user", "content": prompt}], max_tokens=800, system=_SYSTEM_PROMPT, model=HAIKU, context="recommendations/personal")
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start >= 0 and end > start: return json.loads(raw[start:end])
    raise ValueError("Failed to parse recommendation response")
