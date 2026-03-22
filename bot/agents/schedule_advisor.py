"""Smart Schedule advisor: recommend optimal posting times."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

COLD_START_SLOTS = [
    {"day": "monday", "hour_utc": 6, "hour_msk": 9, "score": 0.75, "reason": "Начало недели, утренний ритуал"},
    {"day": "wednesday", "hour_utc": 10, "hour_msk": 13, "score": 0.70, "reason": "Середина недели, обеденный перерыв"},
    {"day": "friday", "hour_utc": 16, "hour_msk": 19, "score": 0.72, "reason": "Вечер пятницы, подготовка к выходным"},
    {"day": "tuesday", "hour_utc": 7, "hour_msk": 10, "score": 0.65, "reason": "Утро вторника, рабочий ритм"},
    {"day": "thursday", "hour_utc": 17, "hour_msk": 20, "score": 0.63, "reason": "Вечер четверга, предвкушение выходных"},
]

TOPIC_TIME_HINTS = {
    "сон": {"preferred_hours": [19, 20, 21], "reason": "Вечерний контент про сон лучше резонирует"},
    "сна": {"preferred_hours": [19, 20, 21], "reason": "Вечерний контент про сон лучше резонирует"},
    "sleep": {"preferred_hours": [19, 20, 21], "reason": "Evening sleep content performs best"},
    "утро": {"preferred_hours": [6, 7, 8], "reason": "Утренний контент — утром"},
    "утренн": {"preferred_hours": [6, 7, 8], "reason": "Утренний контент — утром"},
    "morning": {"preferred_hours": [6, 7, 8], "reason": "Morning content in the morning"},
    "стресс": {"preferred_hours": [12, 13, 17, 18], "reason": "Контент про стресс — в пиковые часы напряжения"},
    "медитация": {"preferred_hours": [6, 7, 20, 21], "reason": "Медитация — утро или вечер"},
    "meditation": {"preferred_hours": [6, 7, 20, 21], "reason": "Meditation content — morning or evening"},
    "энергия": {"preferred_hours": [8, 9, 10], "reason": "Энергетический контент — утром"},
    "релаксация": {"preferred_hours": [19, 20, 21], "reason": "Релаксация — вечер"},
}

DAY_NAMES = {
    0: "monday", 1: "tuesday", 2: "wednesday",
    3: "thursday", 4: "friday", 5: "saturday", 6: "sunday",
}


def _get_topic_hint(topic: str) -> dict | None:
    topic_lower = topic.lower()
    for keyword, hint in TOPIC_TIME_HINTS.items():
        if keyword in topic_lower:
            return hint
    return None


async def recommend_schedule(
    topic: str,
    platform: str = "instagram",
    kind: str = "instagram",
    team_id: str | None = None,
    top_k: int = 3,
) -> dict:
    historical_slots = []
    cold_start = True

    if team_id:
        try:
            from bot.services.social_trends_store import get_best_posting_times
            best_times = await get_best_posting_times(team_id, platform, period_days=30)
            if best_times:
                cold_start = False
                for bt in best_times[:5]:
                    hour = bt.get("hour", 12)
                    day_num = bt.get("weekday", 0)
                    avg_engagement = bt.get("avg_engagement", 0)
                    historical_slots.append({
                        "day": DAY_NAMES.get(day_num, "monday"),
                        "hour_utc": hour,
                        "hour_msk": (hour + 3) % 24,
                        "score": min(1.0, avg_engagement / 100) if avg_engagement else 0.5,
                        "reason": f"Исторически высокий engagement ({avg_engagement:.0f})",
                        "source": "historical",
                    })
        except Exception:
            logger.debug("Failed to get historical posting times", exc_info=True)

    topic_hint = _get_topic_hint(topic)

    if cold_start:
        slots = list(COLD_START_SLOTS)
        if topic_hint:
            for slot in slots:
                if slot["hour_msk"] in topic_hint["preferred_hours"]:
                    slot["score"] = min(1.0, slot["score"] + 0.15)
                    slot["reason"] = topic_hint["reason"]
        slots.sort(key=lambda s: s["score"], reverse=True)
        return {"slots": slots[:top_k], "cold_start": True, "topic_hint": topic_hint["reason"] if topic_hint else None}

    if topic_hint:
        for slot in historical_slots:
            if slot["hour_msk"] in topic_hint["preferred_hours"]:
                slot["score"] = min(1.0, slot["score"] + 0.2)
                slot["reason"] += f" + {topic_hint['reason']}"

    historical_slots.sort(key=lambda s: s["score"], reverse=True)
    return {"slots": historical_slots[:top_k], "cold_start": False, "topic_hint": topic_hint["reason"] if topic_hint else None}
