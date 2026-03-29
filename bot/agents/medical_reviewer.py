"""Medical Reviewer agent — checks cards for unsafe medical claims and missing safety info."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_FORBIDDEN_WORDS = [
    "лечит",
    "излечивает",
    "вылечивает",
    "исцеляет",
    "терапия рака",
    "лечение диабета",
    "лечение covid",
]

_DOCTOR_SYSTEM_PROMPT = """Ты — врач и медицинский редактор. Проверяй карточку ароматерапии.
Флаги:
1. Есть ли недопустимые медицинские обещания (лечит, излечивает, вылечивает)?
2. Указаны ли противопоказания там, где они нужны (беременность, дети, эпилепсия)?
3. Нет ли опасных комбинаций или рекомендаций?

Верни СТРОГО КОМПАКТНЫЙ JSON в одну строку без переносов строк:
{"passed": true, "score": 0.9, "issues": ["issue1"], "corrections": {}}
Если данных недостаточно — {"passed": true, "score": 0.8, "issues": [], "corrections": {}}.
"""

_CATEGORIES_REQUIRING_PRECAUTIONS = {"aroma", "blend", "symptom"}

_BLEND_REVIEW_PROMPT = """\
Ты — врач-консультант. Оцени безопасность смеси эфирных масел.

Задача смеси: {brief}
Желаемые эффекты: {effects}
Способ применения: {application}
Ограничения пользователя: {contraindications}

Верни строго в формате JSON:
{{
  "status": "safe",
  "summary": "Краткая оценка безопасности. 1-2 предложения.",
  "restrictions": [
    {{
      "condition": "эпилепсия",
      "oils_to_exclude": ["Розмарин", "Мята"]
    }}
  ]
}}

status может быть: "safe" | "caution" | "warning"
Ограничения только для реальных медицинских противопоказаний.
Язык: краткий и понятный, без медицинского жаргона.
"""

_APP_LABELS_MEDICAL = {"diffuser": "диффузор", "topical": "нанесение на кожу", "internal": "приём внутрь"}


def review_blend_sync(
    brief: str,
    effects: list[str],
    contraindications: str,
    reference_context: str,
) -> dict:
    """Synchronous medical review of a blend request."""
    from bot.services.claude_client import call_claude

    prompt = _BLEND_REVIEW_PROMPT.format(
        brief=brief,
        effects=", ".join(effects) if effects else "общее применение",
        application="диффузор",
        contraindications=contraindications or "не указаны",
    )

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        context="blend_constructor/doctor",
    )

    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        cleaned = _clean_json(raw[start:end])
        return json.loads(cleaned)
    return {"status": "safe", "summary": "Оценка недоступна.", "restrictions": []}


def _rule_based_check(card: dict[str, Any]) -> tuple[float, list[str], bool]:
    """Returns (score, issues, needs_llm)."""
    issues: list[str] = []
    score = 1.0
    needs_llm = False

    # Check for forbidden medical claims across all text fields
    text_fields = [
        str(card.get("description", "") or ""),
        str(card.get("description_short", "") or ""),
        str(card.get("therapeutic_properties", "") or ""),
        str(card.get("applications", "") or ""),
        str(card.get("indications", "") or ""),
        str(card.get("goal", "") or ""),
    ]
    full_text = " ".join(text_fields).lower()

    for word in _FORBIDDEN_WORDS:
        if word in full_text:
            issues.append(f"CRITICAL: forbidden medical claim found: '{word}'")
            score -= 0.4

    # Check if aroma card is missing precautions/contraindications
    category = str(card.get("category", "") or "").lower()
    if category == "aroma":
        has_precautions = bool(card.get("precautions") or card.get("contraindications"))
        if not has_precautions:
            needs_llm = True  # Ask LLM to evaluate if precautions are needed

    return max(0.0, round(score, 2)), issues, needs_llm


def _clean_json(raw_json: str) -> str:
    """Replace literal newlines inside JSON string values to fix Claude formatting."""
    return re.sub(
        r'"((?:[^"\\]|\\.)*)"',
        lambda m: '"' + m.group(1).replace('\n', ' ').replace('\r', '') + '"',
        raw_json,
    )


def review_card_medical_sync(card: dict[str, Any]) -> dict[str, Any]:
    """Synchronous medical review. Rule-based + optional LLM check.

    Returns:
        {"passed": bool, "score": float, "issues": list[str], "corrections": dict}
    """
    score, issues, needs_llm = _rule_based_check(card)

    # If critical issues found by rule-based check, skip LLM (already failed)
    has_critical = any("CRITICAL" in i for i in issues)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("ANTHROPIC_API_KEY not set — skipping LLM medical review")
        return {
            "passed": score >= 0.7 and not has_critical,
            "score": score,
            "issues": issues,
            "corrections": {},
        }

    if needs_llm or not has_critical:
        try:
            from bot.services.claude_client import call_claude

            card_summary = {
                "name": card.get("name"),
                "category": card.get("category"),
                "description_short": (str(card.get("description_short") or ""))[:200],
                "therapeutic_properties": (str(card.get("therapeutic_properties") or ""))[:300],
                "applications": (str(card.get("applications") or ""))[:200],
                "precautions": (str(card.get("precautions") or ""))[:200],
                "contraindications": (str(card.get("contraindications") or ""))[:200],
                "indications": (str(card.get("indications") or ""))[:200],
            }

            from bot.services.claude_client import call_claude
            raw = call_claude(
                messages=[
                    {
                        "role": "user",
                        "content": f"Проверь карточку на медицинскую безопасность:\n{json.dumps(card_summary, ensure_ascii=False, indent=2)}",
                    }
                ],
                max_tokens=512,
                system=_DOCTOR_SYSTEM_PROMPT,
                context="medical_reviewer",
            )
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(_clean_json(raw[start:end]))
                llm_score = float(result.get("score", 1.0))
                final_score = round(min(score, llm_score), 2)
                all_issues = issues + list(result.get("issues") or [])
                all_corrections = dict(result.get("corrections") or {})
                has_critical_final = any("CRITICAL" in i for i in all_issues)
                return {
                    "passed": final_score >= 0.7 and not has_critical_final,
                    "score": final_score,
                    "issues": all_issues,
                    "corrections": all_corrections,
                }
        except Exception as e:
            logger.warning("LLM medical review failed: %s", e)

    return {
        "passed": score >= 0.7 and not has_critical,
        "score": score,
        "issues": issues,
        "corrections": {},
    }


async def review_card_medical(card: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Async wrapper around review_card_medical_sync.

    Args:
        card: Card dict with category, name, description, precautions, etc.
        dry_run: If True, only run rule-based checks (no LLM call).

    Returns:
        {"passed": bool, "score": float, "issues": list[str], "corrections": dict}
    """
    if dry_run:
        score, issues, _ = _rule_based_check(card)
        has_critical = any("CRITICAL" in i for i in issues)
        return {
            "passed": score >= 0.7 and not has_critical,
            "score": score,
            "issues": issues,
            "corrections": {},
        }

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, review_card_medical_sync, card)
