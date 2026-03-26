"""Wellness Expert agent -- verifies content accuracy for crystal therapy and sound healing."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_CRYSTAL_EXPERT_PROMPT = """Ты -- сертифицированный литотерапевт и эксперт по кристаллотерапии с 10+ летним опытом.
Верифицируй точность данных карточки кристалла. Оцени по шкале 0-1.

Проверяй:
1. Корректность терапевтических и психологических свойств кристалла
2. Правильность ассоциаций с чакрами
3. Точность минералогических данных (твёрдость, кристаллическая система)
4. Наличие важных противопоказаний и мер безопасности
5. Отсутствие медицинских утверждений о лечении заболеваний

Верни JSON строго в формате:
{
  "passed": true/false,
  "score": 0.0-1.0,
  "issues": ["issue 1", ...],
  "corrections": {"field": "corrected value"}
}
"""

_SOUND_EXPERT_PROMPT = """Ты -- сертифицированный звукотерапевт с 10+ летним опытом работы с поющими чашами, гонгами и другими инструментами.
Верифицируй точность данных карточки звукового инструмента/практики. Оцени по шкале 0-1.

Проверяй:
1. Корректность терапевтических свойств (evidence-based)
2. Точность указанных частотных диапазонов
3. Адекватность рекомендуемой длительности сеанса
4. Полноту противопоказаний (эпилепсия, беременность, импланты)
5. Отсутствие псевдонаучных утверждений

Верни JSON строго в формате:
{
  "passed": true/false,
  "score": 0.0-1.0,
  "issues": ["issue 1", ...],
  "corrections": {"field": "corrected value"}
}
"""

# Known crystal systems for validation
_CRYSTAL_SYSTEMS = {
    "кубическая", "тригональная", "гексагональная",
    "тетрагональная", "ромбическая", "моноклинная",
    "триклинная", "аморфная",
}

# Known Mohs hardness ranges for common crystals
_HARDNESS_RANGES: dict[str, tuple[float, float]] = {
    "quartz": (6.5, 7.5),
    "feldspar": (6.0, 6.5),
    "gypsum": (1.5, 2.5),
    "tourmaline": (7.0, 7.5),
    "silicate": (5.0, 7.0),
    "carbonate": (3.0, 4.5),
    "halide": (3.5, 4.5),
    "oxide": (5.5, 6.5),
    "volcanic_glass": (5.0, 6.0),
}

# Known sound source types
_SOUND_SOURCE_TYPES = {
    "gong", "singing_bowl", "tuning_fork", "drum",
    "voice_healing", "binaural", "sound", "instrument",
}

# Known crystal source types
_CRYSTAL_SOURCE_TYPES = {
    "quartz", "tourmaline", "gypsum", "feldspar", "silicate",
    "carbonate", "halide", "oxide", "volcanic_glass",
}


def _basic_crystal_verify(card: dict[str, Any]) -> tuple[float, list[str], dict[str, str]]:
    """Quick rule-based verification for crystal cards (no LLM)."""
    issues: list[str] = []
    corrections: dict[str, str] = {}
    score = 1.0

    payload = card.get("payload") or card
    source_type = str(card.get("source_type") or "").strip().lower()

    # Check source_type
    if source_type and source_type not in _CRYSTAL_SOURCE_TYPES:
        issues.append(
            f"source_type '{source_type}' is not a known crystal type "
            f"(expected: {', '.join(sorted(_CRYSTAL_SOURCE_TYPES))})"
        )
        score -= 0.15

    # Check crystal system
    crystal_system = str(payload.get("crystal_system") or "").strip().lower()
    if crystal_system and crystal_system not in _CRYSTAL_SYSTEMS:
        issues.append(f"crystal_system '{crystal_system}' is not standard")
        score -= 0.2

    # Validate hardness against expected range for source_type
    hardness = payload.get("hardness")
    if hardness is not None and source_type in _HARDNESS_RANGES:
        low, high = _HARDNESS_RANGES[source_type]
        if not (low - 1 <= float(hardness) <= high + 1):
            issues.append(
                f"hardness {hardness} seems unusual for {source_type} "
                f"(expected ~{low}-{high})"
            )
            score -= 0.15

    # Check required fields
    if not payload.get("therapeutic_properties"):
        issues.append("missing therapeutic_properties")
        score -= 0.2
    if not payload.get("chakras"):
        issues.append("missing chakras")
        score -= 0.1
    if not payload.get("care_instructions"):
        issues.append("missing care_instructions")
        score -= 0.1
    if not payload.get("color"):
        issues.append("missing color")
        score -= 0.05

    return max(0.0, round(score, 2)), issues, corrections


def _basic_sound_verify(card: dict[str, Any]) -> tuple[float, list[str], dict[str, str]]:
    """Quick rule-based verification for sound healing cards (no LLM)."""
    issues: list[str] = []
    corrections: dict[str, str] = {}
    score = 1.0

    payload = card.get("payload") or card
    source_type = str(card.get("source_type") or "").strip().lower()

    if source_type and source_type not in _SOUND_SOURCE_TYPES:
        issues.append(
            f"source_type '{source_type}' is not a known sound type "
            f"(expected: {', '.join(sorted(_SOUND_SOURCE_TYPES))})"
        )
        score -= 0.15

    if not payload.get("therapeutic_properties"):
        issues.append("missing therapeutic_properties")
        score -= 0.2
    if not payload.get("contraindications") and source_type in ("gong", "singing_bowl", "tuning_fork", "binaural"):
        issues.append("missing contraindications for instrument that typically requires them")
        score -= 0.15
    if not payload.get("session_duration"):
        issues.append("missing session_duration")
        score -= 0.1

    return max(0.0, round(score, 2)), issues, corrections


async def verify_wellness_content(
    card_data: dict[str, Any],
    category: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Validate content accuracy for crystal therapy and sound healing.

    Args:
        card_data: Card dict with payload fields.
        category: One of 'crystal' or 'sound'.
        dry_run: If True, only run rule-based checks (no LLM call).

    Returns:
        {"valid": bool, "issues": [...], "suggestions": [...], "confidence": float}
    """
    if category == "crystal":
        score, issues, corrections = _basic_crystal_verify(card_data)
        system_prompt = _CRYSTAL_EXPERT_PROMPT
    elif category == "sound":
        score, issues, corrections = _basic_sound_verify(card_data)
        system_prompt = _SOUND_EXPERT_PROMPT
    else:
        return {
            "valid": False,
            "issues": [f"unsupported category: {category}"],
            "suggestions": [],
            "confidence": 0.0,
        }

    if dry_run:
        return {
            "valid": score >= 0.7,
            "issues": issues,
            "suggestions": list(corrections.values()),
            "confidence": score,
        }

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("ANTHROPIC_API_KEY not set -- using rule-based verification only")
        return {
            "valid": score >= 0.7,
            "issues": issues,
            "suggestions": list(corrections.values()),
            "confidence": score,
        }

    try:
        from bot.services.claude_client import call_claude

        # Build a concise summary for verification
        payload = card_data.get("payload") or card_data
        summary = {
            "name": card_data.get("name"),
            "source_type": card_data.get("source_type"),
            "description_short": str(payload.get("description_short") or "")[:200],
            "therapeutic_properties": payload.get("therapeutic_properties"),
            "contraindications": payload.get("contraindications"),
        }
        if category == "crystal":
            summary["chakras"] = payload.get("chakras")
            summary["hardness"] = payload.get("hardness")
            summary["crystal_system"] = payload.get("crystal_system")
            summary["complementary_oils"] = payload.get("complementary_oils")
        elif category == "sound":
            summary["frequency_range"] = payload.get("frequency_range")
            summary["session_duration"] = payload.get("session_duration")

        raw = call_claude(
            messages=[
                {
                    "role": "user",
                    "content": f"Верифицируй карточку:\n{json.dumps(summary, ensure_ascii=False, indent=2)}",
                }
            ],
            max_tokens=512,
            system=system_prompt,
            context="wellness_expert",
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
                "valid": final_score >= 0.7,
                "issues": all_issues,
                "suggestions": list(all_corrections.values()),
                "confidence": final_score,
            }
    except Exception as e:
        logger.warning("LLM verification failed: %s", e)

    return {
        "valid": score >= 0.7,
        "issues": issues,
        "suggestions": list(corrections.values()),
        "confidence": score,
    }
