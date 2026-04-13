"""Sound Healing Expert agent — deep verification for gongs, singing bowls, and sound therapy."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_EXPERT_SYSTEM_PROMPT = """Ты — сертифицированный звукотерапевт и мастер гонг-медитации с 15+ летним опытом.
Специализация: гонги (планетарные, симфонические, ветровые), тибетские поющие чаши,
кристаллические чаши, камертоны, голосовые практики (обертонное пение, тонинг),
бинауральные ритмы, звуковые ванны.

Верифицируй точность данных карточки звукового инструмента/практики. Оцени по шкале 0–1.

Проверяй:
1. Корректность указанных частот и обертонов (планетарные гонги — частоты по Кусто)
2. Точность терапевтических свойств — только evidence-based эффекты
3. Правильность и полноту противопоказаний:
   - Эпилепсия и судорожные состояния
   - Беременность (особенно гонги — вибрация)
   - Металлические импланты и кардиостимуляторы
   - Психические расстройства в остром периоде
   - Тяжёлые сердечно-сосудистые заболевания
   - Менингит, опухоли головного мозга
4. Адекватность длительности сеанса для данного инструмента
5. Правильность рекомендаций по расстоянию и расположению
6. Отсутствие псевдонаучных утверждений (чакры допустимы как метафора, не как медицина)
7. Корректность ноты/тональности для чаш и камертонов

Верни JSON строго в формате:
{
  "passed": true/false,
  "score": 0.0–1.0,
  "issues": ["issue 1", ...],
  "corrections": {"field": "corrected value"}
}

Если данных недостаточно для оценки — верни score: 0.5, passed: true, issues: [].
"""

# ── Instrument types ────────────────────────────────────────────────
_GONG_TYPES = {
    "planetary_gong", "symphonic_gong", "wind_gong", "opera_gong",
    "chau_gong", "nipple_gong", "tiger_gong",
}

_BOWL_TYPES = {
    "tibetan_singing_bowl", "crystal_singing_bowl", "himalayan_bowl",
    "japanese_rin", "bronze_bowl",
}

_TUNING_TYPES = {
    "tuning_fork", "weighted_tuning_fork", "otto_tuning_fork",
    "solfeggio_fork", "brain_tuner",
}

_VOICE_TYPES = {
    "overtone_singing", "toning", "mantra", "vocal_harmonics",
    "humming", "chanting",
}

_OTHER_SOUND_TYPES = {
    "binaural_beats", "isochronic_tones", "sound_bath",
    "drum_journey", "frame_drum", "ocean_drum", "rain_stick",
    "shruti_box", "monochord", "koshi_chime", "tingsha",
    "didgeridoo", "hang_drum", "handpan", "kalimba",
}

_ALL_SOUND_TYPES = (
    _GONG_TYPES | _BOWL_TYPES | _TUNING_TYPES |
    _VOICE_TYPES | _OTHER_SOUND_TYPES |
    # Legacy types from wellness_expert for compatibility
    {"gong", "singing_bowl", "tuning_fork", "drum",
     "voice_healing", "binaural", "sound", "instrument"}
)

# ── Frequency ranges (Hz) for validation ────────────────────────────
_FREQUENCY_RANGES: dict[str, tuple[float, float]] = {
    "planetary_gong": (20, 500),
    "symphonic_gong": (30, 800),
    "tibetan_singing_bowl": (110, 660),
    "crystal_singing_bowl": (220, 880),
    "tuning_fork": (64, 4096),
    "binaural_beats": (1, 40),  # difference frequency
    "didgeridoo": (50, 200),
}

# ── Standard session durations (minutes) ────────────────────────────
_SESSION_DURATION_RANGES: dict[str, tuple[int, int]] = {
    "gong": (15, 90),
    "planetary_gong": (20, 90),
    "singing_bowl": (15, 60),
    "tibetan_singing_bowl": (15, 60),
    "crystal_singing_bowl": (15, 45),
    "tuning_fork": (5, 30),
    "binaural_beats": (10, 60),
    "sound_bath": (30, 90),
    "drum_journey": (15, 60),
}

# ── Critical contraindications ──────────────────────────────────────
_CRITICAL_CONTRAINDICATIONS_HIGH_VIBRATION = [
    "эпилепсия", "беременность", "кардиостимулятор",
]
_CRITICAL_CONTRAINDICATIONS_ALL = [
    "эпилепсия", "острые психические расстройства",
]

# Instruments with high vibration impact requiring stricter contraindications
_HIGH_VIBRATION_INSTRUMENTS = (
    _GONG_TYPES | {"gong"} | {"didgeridoo"} |
    {"tibetan_singing_bowl", "singing_bowl"}
)


def _basic_verify(card: dict[str, Any]) -> tuple[float, list[str], dict[str, str]]:
    """Quick rule-based verification without calling Claude."""
    issues: list[str] = []
    corrections: dict[str, str] = {}
    score = 1.0

    payload = card.get("payload") or card

    # ── source_type validation ──────────────────────────────────────
    source_type = str(card.get("source_type") or "").strip().lower()
    if source_type and source_type not in _ALL_SOUND_TYPES:
        issues.append(
            f"source_type '{source_type}' is not a known sound healing type"
        )
        score -= 0.15

    # ── Required fields ─────────────────────────────────────────────
    if not payload.get("therapeutic_properties"):
        issues.append("missing therapeutic_properties")
        score -= 0.2

    if not payload.get("description") and not payload.get("description_short"):
        issues.append("missing description")
        score -= 0.15

    # ── Contraindications — stricter for high-vibration instruments ─
    contra_text = str(payload.get("contraindications") or "").lower()
    if source_type in _HIGH_VIBRATION_INSTRUMENTS:
        if not contra_text:
            issues.append(
                f"missing contraindications — critical for high-vibration instrument '{source_type}'"
            )
            score -= 0.25
        else:
            missing = [c for c in _CRITICAL_CONTRAINDICATIONS_HIGH_VIBRATION if c not in contra_text]
            if missing:
                issues.append(f"contraindications missing critical items for high-vibration: {', '.join(missing)}")
                score -= 0.15
    else:
        if not contra_text:
            issues.append("missing contraindications")
            score -= 0.15
        else:
            missing = [c for c in _CRITICAL_CONTRAINDICATIONS_ALL if c not in contra_text]
            if missing:
                issues.append(f"contraindications missing: {', '.join(missing)}")
                score -= 0.1

    # ── Session duration ────────────────────────────────────────────
    duration = payload.get("session_duration")
    if not duration:
        issues.append("missing session_duration")
        score -= 0.1
    elif source_type in _SESSION_DURATION_RANGES:
        try:
            dur_min = int(str(duration).split("-")[0].strip().split()[0])
            low, high = _SESSION_DURATION_RANGES[source_type]
            if dur_min < low - 5 or dur_min > high + 15:
                issues.append(
                    f"session_duration {duration} seems unusual for {source_type} "
                    f"(typical: {low}-{high} min)"
                )
                score -= 0.1
        except (ValueError, IndexError):
            pass  # Can't parse — skip numeric check

    # ── Frequency validation ────────────────────────────────────────
    freq = payload.get("frequency_range") or payload.get("frequency")
    if freq and source_type in _FREQUENCY_RANGES:
        try:
            freq_val = float(str(freq).split("-")[0].strip().split()[0])
            low, high = _FREQUENCY_RANGES[source_type]
            if freq_val < low * 0.5 or freq_val > high * 2:
                issues.append(
                    f"frequency {freq} seems far outside typical range for {source_type} "
                    f"(expected ~{low}-{high} Hz)"
                )
                score -= 0.1
        except (ValueError, IndexError):
            pass

    # ── Note/tonality for bowls and forks ───────────────────────────
    if source_type in (_BOWL_TYPES | _TUNING_TYPES | {"singing_bowl", "tuning_fork"}):
        if not payload.get("note") and not payload.get("tonality"):
            issues.append("bowls/forks should specify note or tonality")
            score -= 0.05

    return max(0.0, round(score, 2)), issues, corrections


async def verify_sound_content(
    card_data: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Verify sound healing card content.

    Args:
        card_data: Card dict with payload fields.
        dry_run: If True, only run rule-based checks (no LLM call).

    Returns:
        {"passed": bool, "score": float, "issues": list[str], "corrections": dict}
    """
    score, issues, corrections = _basic_verify(card_data)

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
            "source_type": card_data.get("source_type"),
            "description_short": str(payload.get("description_short") or "")[:200],
            "therapeutic_properties": str(payload.get("therapeutic_properties") or "")[:300],
            "contraindications": str(payload.get("contraindications") or "")[:300],
            "frequency_range": payload.get("frequency_range") or payload.get("frequency"),
            "session_duration": payload.get("session_duration"),
            "note": payload.get("note") or payload.get("tonality"),
            "playing_technique": payload.get("playing_technique"),
            "recommended_distance": payload.get("recommended_distance"),
        }

        raw = call_claude(
            messages=[
                {
                    "role": "user",
                    "content": f"Верифицируй карточку звукового инструмента:\n{json.dumps(summary, ensure_ascii=False, indent=2)}",
                }
            ],
            max_tokens=512,
            system=_EXPERT_SYSTEM_PROMPT,
            context="sound_healing_expert",
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
        logger.warning("LLM sound healing verification failed: %s", e)

    return {
        "passed": score >= 0.7,
        "score": score,
        "issues": issues,
        "corrections": corrections,
    }
