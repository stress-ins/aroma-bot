"""Bodywork Expert agent — verifies card content for massage, osteopathy, and biodynamics."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_EXPERT_SYSTEM_PROMPT = """Ты — сертифицированный специалист по телесным практикам с 15+ летним опытом:
массаж (классический, спортивный, лимфодренажный, висцеральный), остеопрактика
(краниосакральная, структуральная, висцеральная), биодинамика.

Верифицируй точность данных карточки телесной практики. Оцени по шкале 0–1.

Проверяй:
1. Анатомическую корректность описания техники и зон воздействия
2. Полноту и точность противопоказаний (тромбоз, онкология, беременность, остеопороз, грыжи)
3. Корректность указания давления и интенсивности для данной техники
4. Адекватность рекомендуемой длительности сеанса
5. Соответствие уровня сложности описанию техники
6. Отсутствие опасных рекомендаций для самостоятельного выполнения

Верни JSON строго в формате:
{
  "passed": true/false,
  "score": 0.0–1.0,
  "issues": ["issue 1", ...],
  "corrections": {"field": "corrected value"}
}

Если данных недостаточно для оценки — верни score: 0.5, passed: true, issues: [].
"""

# ── Known source types ──────────────────────────────────────────────
_MASSAGE_SOURCE_TYPES = {
    "classical", "sports", "lymphatic", "visceral", "deep_tissue",
    "trigger_point", "myofascial", "thai", "shiatsu", "aroma_massage",
    "reflexology", "facial", "prenatal", "pediatric", "cupping",
}

_OSTEO_SOURCE_TYPES = {
    "craniosacral", "structural", "visceral_osteo", "biodynamic_osteo",
    "fascial", "functional", "muscle_energy",
}

_BIODYNAMICS_SOURCE_TYPES = {
    "biodynamic_cranial", "biodynamic_breath", "tissue_memory",
    "fluid_dynamics", "embryological",
}

_ALL_BODYWORK_TYPES = _MASSAGE_SOURCE_TYPES | _OSTEO_SOURCE_TYPES | _BIODYNAMICS_SOURCE_TYPES

# ── Body zones ──────────────────────────────────────────────────────
_VALID_BODY_ZONES = {
    "голова", "лицо", "шея", "плечи", "спина", "поясница",
    "грудная клетка", "живот", "руки", "кисти", "ноги",
    "стопы", "всё тело", "таз", "крестец",
}

# ── Difficulty levels ───────────────────────────────────────────────
_DIFFICULTY_LEVELS = {"начинающий", "средний", "продвинутый", "специалист"}

# ── Pressure levels ─────────────────────────────────────────────────
_PRESSURE_LEVELS = {"лёгкое", "среднее", "глубокое", "без давления", "переменное"}

# ── Critical contraindications that MUST be present ─────────────────
_CRITICAL_CONTRAINDICATIONS = {
    "massage": ["тромбоз", "онкология", "острое воспаление", "лихорадка"],
    "osteo": ["тромбоз", "онкология", "аневризма", "острый инсульт"],
    "biodynamics": ["онкология", "острый психоз"],
}


def _basic_verify(card: dict[str, Any], category: str) -> tuple[float, list[str], dict[str, str]]:
    """Quick rule-based verification without calling Claude."""
    issues: list[str] = []
    corrections: dict[str, str] = {}
    score = 1.0

    payload = card.get("payload") or card

    # ── source_type validation ──────────────────────────────────────
    source_type = str(card.get("source_type") or "").strip().lower()
    if category == "massage":
        valid_types = _MASSAGE_SOURCE_TYPES
    elif category == "osteo":
        valid_types = _OSTEO_SOURCE_TYPES
    elif category == "biodynamics":
        valid_types = _BIODYNAMICS_SOURCE_TYPES
    else:
        valid_types = _ALL_BODYWORK_TYPES

    if source_type and source_type not in valid_types:
        issues.append(
            f"source_type '{source_type}' is not a known {category} type "
            f"(expected: {', '.join(sorted(valid_types))})"
        )
        score -= 0.2

    # ── Required fields ─────────────────────────────────────────────
    if not payload.get("therapeutic_properties"):
        issues.append("missing therapeutic_properties")
        score -= 0.2

    if not payload.get("contraindications"):
        issues.append("missing contraindications — critical for bodywork techniques")
        score -= 0.25

    if not payload.get("description") and not payload.get("description_short"):
        issues.append("missing description")
        score -= 0.15

    # ── Duration validation ─────────────────────────────────────────
    duration = payload.get("session_duration") or payload.get("duration")
    if not duration:
        issues.append("missing session_duration")
        score -= 0.1

    # ── Pressure level validation ───────────────────────────────────
    pressure = str(payload.get("pressure_level") or "").strip().lower()
    if pressure and pressure not in _PRESSURE_LEVELS:
        issues.append(f"pressure_level '{pressure}' is not standard")
        score -= 0.1

    # ── Difficulty level validation ─────────────────────────────────
    difficulty = str(payload.get("difficulty_level") or "").strip().lower()
    if difficulty and difficulty not in _DIFFICULTY_LEVELS:
        issues.append(f"difficulty_level '{difficulty}' is not standard")
        score -= 0.1

    # ── Critical contraindications check ────────────────────────────
    contra_text = str(payload.get("contraindications") or "").lower()
    if contra_text:
        required = _CRITICAL_CONTRAINDICATIONS.get(category, _CRITICAL_CONTRAINDICATIONS["massage"])
        missing = [c for c in required if c not in contra_text]
        if missing:
            issues.append(f"contraindications missing critical items: {', '.join(missing)}")
            score -= 0.15

    return max(0.0, round(score, 2)), issues, corrections


async def verify_bodywork_content(
    card_data: dict[str, Any],
    category: str = "massage",
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Verify bodywork card content (massage, osteo, biodynamics).

    Args:
        card_data: Card dict with payload fields.
        category: One of 'massage', 'osteo', 'biodynamics'.
        dry_run: If True, only run rule-based checks (no LLM call).

    Returns:
        {"passed": bool, "score": float, "issues": list[str], "corrections": dict}
    """
    if category not in ("massage", "osteo", "biodynamics"):
        return {
            "passed": False,
            "score": 0.0,
            "issues": [f"unsupported bodywork category: {category}"],
            "corrections": {},
        }

    score, issues, corrections = _basic_verify(card_data, category)

    if dry_run:
        return {
            "passed": score >= 0.7,
            "score": score,
            "issues": issues,
            "corrections": corrections,
        }

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("ANTHROPIC_API_KEY not set — skipping LLM verification")
        return {
            "passed": score >= 0.7,
            "score": score,
            "issues": issues,
            "corrections": corrections,
        }

    try:
        from bot.services.claude_client import call_claude

        payload = card_data.get("payload") or card_data
        summary = {
            "name": card_data.get("name"),
            "category": category,
            "source_type": card_data.get("source_type"),
            "description_short": str(payload.get("description_short") or "")[:200],
            "therapeutic_properties": str(payload.get("therapeutic_properties") or "")[:300],
            "contraindications": str(payload.get("contraindications") or "")[:300],
            "body_zones": payload.get("body_zones"),
            "pressure_level": payload.get("pressure_level"),
            "duration": payload.get("session_duration") or payload.get("duration"),
            "difficulty_level": payload.get("difficulty_level"),
            "complementary_oils": payload.get("complementary_oils"),
        }

        raw = call_claude(
            messages=[
                {
                    "role": "user",
                    "content": f"Верифицируй карточку телесной практики:\n{json.dumps(summary, ensure_ascii=False, indent=2)}",
                }
            ],
            max_tokens=512,
            system=_EXPERT_SYSTEM_PROMPT,
            context="bodywork_expert",
        )

        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(raw[start:end])
            llm_score = float(result.get("score", 1.0))
            final_score = round(min(score, llm_score), 2)
            all_issues = issues + list(result.get("issues") or [])
            all_corrections = {**corrections, **(result.get("corrections") or {})}
            return {
                "passed": final_score >= 0.7,
                "score": final_score,
                "issues": all_issues,
                "corrections": all_corrections,
            }
    except Exception as e:
        logger.warning("LLM bodywork verification failed: %s", e)

    return {
        "passed": score >= 0.7,
        "score": score,
        "issues": issues,
        "corrections": corrections,
    }
