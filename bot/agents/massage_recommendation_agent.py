"""Recommendation agent — personal massage technique recommendations."""
from __future__ import annotations
import json, logging
logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Ты — эксперт по массажу, остеопрактике и телесным практикам. "
    "ВСЕГДА отвечай ТОЛЬКО на русском языке. "
    "На основе запроса пользователя подбери 3 массажные техники из предоставленного справочника. "
    "Для каждой техники укажи: slug (из справочника), причину выбора (2-3 предложения), "
    "и практическую рекомендацию на сеанс.\n\n"
    "Правила:\n"
    "- Учитывай противопоказания — НИКОГДА не рекомендуй технику при наличии противопоказаний\n"
    "- Если указана конкретная зона тела, отдавай предпочтение техникам для этой зоны\n"
    "- Рекомендуй комплементарные масла для каждой техники\n"
    "- Если пользователь новичок, избегай продвинутых техник (difficulty_level: продвинутый)"
)

_USER_PROMPT = (
    "Отвечай строго на русском языке.\n\n"
    "Что беспокоит: {concern}\n"
    "Зона тела: {body_zone}\n"
    "Цель: {goal}\n"
    "Опыт: {experience}\n"
    "Противопоказания: {contraindications}\n\n"
    "Справочник массажных техник:\n{reference_context}\n\n"
    "Верни строго JSON:\n{{\n"
    "  \"recommendations\": [\n"
    "    {{\"slug\": \"aroma-massage\", \"name_ru\": \"Аромамассаж\", "
    "\"reason\": \"...\", \"session_advice\": \"...\", "
    "\"oils\": [\"lavender\", \"bergamot\"]}},\n"
    "    ...\n"
    "  ],\n"
    "  \"general_advice\": \"...\"\n"
    "}}"
)

_CONCERN = {
    "pain": "боль / напряжение в мышцах",
    "stress": "стресс / эмоциональное напряжение",
    "stiffness": "скованность / ограниченная подвижность",
    "recovery": "восстановление после нагрузки",
    "relaxation": "расслабление / улучшение сна",
    "headache": "головная боль / мигрень",
}

_ZONE = {
    "back": "спина и поясница",
    "neck": "шея и голова",
    "feet": "стопы",
    "face": "лицо",
    "abdomen": "живот",
    "full_body": "всё тело",
    "legs": "ноги",
}

_GOAL = {
    "relieve_pain": "снять боль",
    "relax": "расслабиться",
    "restore": "восстановиться",
    "improve_mobility": "улучшить подвижность",
    "detox": "детоксикация",
}

_EXPERIENCE = {
    "beginner": "новичок (первый раз)",
    "some": "есть опыт массажа",
    "experienced": "опытный практик",
}


def recommend_massage_sync(
    concern: str,
    body_zone: str,
    goal: str,
    experience: str,
    contraindications: str,
    reference_context: str,
) -> dict:
    from bot.services.claude_client import HAIKU, call_claude

    prompt = _USER_PROMPT.format(
        concern=_CONCERN.get(concern, concern),
        body_zone=_ZONE.get(body_zone, body_zone),
        goal=_GOAL.get(goal, goal),
        experience=_EXPERIENCE.get(experience, experience),
        contraindications=contraindications or "нет",
        reference_context=reference_context[:4000],
    )
    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        system=_SYSTEM_PROMPT,
        model=HAIKU,
        context="recommendations/massage",
    )
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(raw[start:end])
    raise ValueError("Failed to parse massage recommendation response")
