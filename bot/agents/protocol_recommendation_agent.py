"""Multimodal protocol recommendation agent — oil + massage + sound + crystal."""
from __future__ import annotations
import json, logging
logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Ты — эксперт по мультимодальным оздоровительным протоколам, объединяющий "
    "ароматерапию, массаж, звукотерапию и кристаллотерапию. "
    "ВСЕГДА отвечай ТОЛЬКО на русском языке.\n\n"
    "На основе запроса пользователя составь комплексный протокол из 4 модальностей:\n"
    "1. Эфирное масло (из раздела «Ароматы»)\n"
    "2. Массажная техника (из раздела «Массаж»)\n"
    "3. Звуковой инструмент (из раздела «Звуки»)\n"
    "4. Кристалл (из раздела «Кристаллы»)\n\n"
    "Правила:\n"
    "- Учитывай противопоказания — НИКОГДА не рекомендуй при их наличии\n"
    "- Объясняй синергию между модальностями (почему именно это сочетание)\n"
    "- Давай практические рекомендации по проведению сеанса\n"
    "- Рекомендуй порядок применения модальностей в сеансе\n"
    "- Указывай длительность каждого этапа"
)

_USER_PROMPT = (
    "Отвечай строго на русском языке.\n\n"
    "Что беспокоит: {concern}\n"
    "Зона тела: {body_zone}\n"
    "Цель: {goal}\n"
    "Предпочитаемые модальности: {modalities}\n"
    "Противопоказания: {contraindications}\n\n"
    "Справочник:\n{reference_context}\n\n"
    "Верни строго JSON:\n{{\n"
    "  \"protocol_name\": \"Название протокола\",\n"
    "  \"protocol_description\": \"Описание протокола (2-3 предложения)\",\n"
    "  \"oil\": {{\"slug\": \"lavender\", \"name_ru\": \"Лаванда\", \"reason\": \"...\", \"usage\": \"как применять\"}},\n"
    "  \"massage\": {{\"slug\": \"aroma-massage\", \"name_ru\": \"Аромамассаж\", \"reason\": \"...\", \"duration_min\": 30}},\n"
    "  \"sound\": {{\"slug\": \"tibetan-singing-bowl\", \"name_ru\": \"Тибетская поющая чаша\", \"reason\": \"...\", \"duration_min\": 15}},\n"
    "  \"crystal\": {{\"slug\": \"amethyst\", \"name_ru\": \"Аметист\", \"reason\": \"...\", \"placement\": \"где разместить\"}},\n"
    "  \"session_plan\": [\n"
    "    {{\"step\": 1, \"modality\": \"oil\", \"action\": \"...\", \"duration_min\": 5}},\n"
    "    {{\"step\": 2, \"modality\": \"crystal\", \"action\": \"...\", \"duration_min\": 5}},\n"
    "    {{\"step\": 3, \"modality\": \"sound\", \"action\": \"...\", \"duration_min\": 15}},\n"
    "    {{\"step\": 4, \"modality\": \"massage\", \"action\": \"...\", \"duration_min\": 30}}\n"
    "  ],\n"
    "  \"synergy\": \"Объяснение синергии между модальностями (2-3 предложения)\",\n"
    "  \"total_duration_min\": 55,\n"
    "  \"general_advice\": \"Общие рекомендации (2-3 предложения)\"\n"
    "}}"
)

CONCERN_OPTIONS = {
    "pain": "боль / напряжение в мышцах",
    "stress": "стресс / эмоциональное напряжение",
    "insomnia": "бессонница / нарушение сна",
    "fatigue": "хроническая усталость / упадок сил",
    "headache": "головная боль / мигрень",
    "anxiety": "тревожность / беспокойство",
    "stiffness": "скованность / ограниченная подвижность",
    "immunity": "слабый иммунитет / частые простуды",
}

ZONE_OPTIONS = {
    "back": "спина и поясница",
    "neck": "шея и голова",
    "full_body": "всё тело",
    "feet": "стопы",
    "abdomen": "живот",
    "chest": "грудная клетка",
}

GOAL_OPTIONS = {
    "relieve": "снять боль и напряжение",
    "relax": "глубокое расслабление",
    "restore": "восстановление энергии",
    "balance": "эмоциональный баланс",
    "heal": "поддержка выздоровления",
}

MODALITY_OPTIONS = {
    "all": "все 4 модальности",
    "oil_massage": "масла + массаж",
    "oil_sound": "масла + звук",
    "oil_crystal": "масла + кристаллы",
    "massage_sound": "массаж + звук",
}


def recommend_protocol_sync(
    concern: str,
    body_zone: str,
    goal: str,
    modalities: str,
    contraindications: str,
    reference_context: str,
) -> dict:
    from bot.services.claude_client import HAIKU, call_claude

    prompt = _USER_PROMPT.format(
        concern=CONCERN_OPTIONS.get(concern, concern),
        body_zone=ZONE_OPTIONS.get(body_zone, body_zone),
        goal=GOAL_OPTIONS.get(goal, goal),
        modalities=MODALITY_OPTIONS.get(modalities, modalities),
        contraindications=contraindications or "нет",
        reference_context=reference_context[:6000],
    )
    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
        system=_SYSTEM_PROMPT,
        model=HAIKU,
        context="recommendations/protocol",
    )
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(raw[start:end])
    raise ValueError("Failed to parse protocol recommendation response")
