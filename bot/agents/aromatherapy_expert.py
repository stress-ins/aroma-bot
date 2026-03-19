"""Aromatherapy Expert agent — verifies card content accuracy against expert knowledge."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_EXPERT_SYSTEM_PROMPT = """Ты — сертифицированный ароматерапевт с 15+ летним опытом и знанием ольфактотерапии.
Верифицируй точность данных карточки эфирного масла согласно принятым стандартам
аромотерапии (NAHA, IFA). Оцени по шкале 0–1.

Проверяй:
1. Корректность терапевтических свойств и противопоказаний
2. Соответствие категоризации (parent_group/category_group) анатомической системе
3. Логичность комплементарных масел
4. Правильность классификации source_type (herb/flower/resin/tree/spice/citrus)

Верни JSON строго в формате:
{
  "passed": true/false,
  "score": 0.0–1.0,
  "issues": ["issue 1", ...],
  "corrections": {"field": "corrected value"}
}

Если данных недостаточно для оценки — верни score: 0.5, passed: true, issues: [].
"""

_KNOWN_SOURCE_TYPES = {"herb", "flower", "resin", "tree", "spice", "citrus", "grass", "root", "wood"}

ANATOMICAL_SYSTEMS = {
    "НЕРВНАЯ СИСТЕМА", "ПИЩЕВАРИТЕЛЬНАЯ СИСТЕМА",
    "СЕРДЕЧНО-СОСУДИСТАЯ СИСТЕМА", "КРОВЕНОСНАЯ И СЕРДЕЧНО-СОСУДИСТАЯ СИСТЕМА",
    "ДЫХАТЕЛЬНАЯ СИСТЕМА", "ОПОРНО-ДВИГАТЕЛЬНЫЙ АППАРАТ", "ОПОРНО-ДВИГАТЕЛЬНАЯ СИСТЕМА",
    "ИММУННАЯ СИСТЕМА", "ЭНДОКРИННАЯ СИСТЕМА", "МОЧЕПОЛОВАЯ СИСТЕМА",
    "РЕПРОДУКТИВНАЯ СИСТЕМА", "КОЖА И ПОКРОВЫ", "ОРГАНЫ ЗРЕНИЯ И СЛУХА",
    "ПСИХОЭМОЦИОНАЛЬНОЕ СОСТОЯНИЕ", "ПСИХИКА И ЭМОЦИИ",
    "СОН И ОТДЫХ", "ЭНЕРГИЯ И ТОНУС", "ЖЕНСКОЕ ЗДОРОВЬЕ", "ДЕТСКОЕ ЗДОРОВЬЕ",
    "ИММУНИТЕТ И КОЖА", "ПИЩЕВАРЕНИЕ", "СЕРДЕЧНО-СОСУДИСТАЯ", "ПСИХОЭМОЦИОНАЛЬНОЕ",
    "ОБЩЕЕ И РАЗНОЕ",
}


def _basic_verify(card: dict[str, Any]) -> tuple[float, list[str], dict[str, str]]:
    """Quick rule-based verification without calling Claude."""
    issues: list[str] = []
    corrections: dict[str, str] = {}
    score = 1.0

    source_type = str(card.get("source_type") or "").strip().lower()
    if source_type and source_type not in _KNOWN_SOURCE_TYPES:
        issues.append(f"source_type '{source_type}' is not standard (expected: {', '.join(sorted(_KNOWN_SOURCE_TYPES))})")
        score -= 0.2

    parent_group = str(card.get("parent_group") or "").strip().upper()
    if parent_group and parent_group not in ANATOMICAL_SYSTEMS:
        # Only flag if it looks like a disease/symptom name rather than a system
        if len(parent_group.split()) <= 3 and not any(word in parent_group for word in ("СИСТЕМА", "ЗДОРОВЬЕ", "СОСТОЯНИЕ", "АППАРАТ", "ОТДЫХ", "ТОНУС", "КОЖА")):
            issues.append(
                f"parent_group '{parent_group}' may not be an anatomical system — expected names like НЕРВНАЯ СИСТЕМА"
            )
            score -= 0.15

    return max(0.0, round(score, 2)), issues, corrections


_CONSTRUCT_BLEND_PROMPT = """\
Ты — эксперт-ароматерапевт. Подбери смесь эфирных масел под задачу.

Задача пользователя: {brief}
Желаемые эффекты: {effects}
Скорость действия: {speed}
Способ применения: {application}
Дополнительные ограничения: {contraindications}{custom_oils_block}

Справочник масел для подбора:
{reference_context}

Верни строго в формате JSON:
{{
  "title": "Название смеси (2-3 слова)",
  "oils": [
    {{
      "name_ru": "Розмарин",
      "name_en": "Rosemary",
      "drops": 3,
      "role": "основа"
    }}
  ],
  "profile": {{
    "focus": 85,
    "energy": 65,
    "creativity": 70,
    "calm": 30
  }},
  "explanation": "Почему именно эти масла и почему связка работает. 2-3 предложения.",
  "application": "Как применять, режим, дозировка. 1-2 предложения.",
  "tags": ["концентрация", "офис"]
}}

Требования к рецепту:
- Итого 6-10 капель
- 3-5 масел, не больше
- Каждое масло имеет роль: основа / усилитель / модификатор / активатор
- Объяснение — живым языком без научных терминов
- Только те масла которые есть в справочнике{custom_oils_require}

Правила применения в поле "application":
- Никогда не упоминай «аромалампу» — используй «диффузор»
- Вместо «нюхать из флакона» — «капните 1-2 капли на ладонь, разотрите и вдыхайте с ладоней»
- При упоминании ванны: «предварительно накапайте масло на морскую соль или добавьте в жирные сливки, затем растворите в воде»
"""


_SPEED_LABELS = {"fast": "быстрое", "medium": "среднее", "extended": "пролонгированное"}
_APP_LABELS = {"diffuser": "диффузор", "topical": "нанесение на кожу", "internal": "приём внутрь", "any": "любой (диффузор, нанесение или приём внутрь)"}


def construct_blend_sync(
    brief: str,
    effects: list[str],
    speed: str,
    application: str,
    contraindications: str,
    reference_context: str,
    custom_oils: list[str] | None = None,
    exclude_oils: list[str] | None = None,
) -> dict:
    """Synchronous blend construction via aromatherapy expert agent."""
    from bot.services.claude_client import SONNET, call_claude

    custom_oils_block = ""
    custom_oils_require = ""
    if custom_oils:
        oils_str = ", ".join(custom_oils)
        custom_oils_block = f"\nМасла которые ОБЯЗАТЕЛЬНО включить в смесь: {oils_str}"
        custom_oils_require = (
            f"\n- ОБЯЗАТЕЛЬНО включи в состав: {oils_str} "
            f"— подбери им подходящую роль и дозировку"
        )
    if exclude_oils:
        exclude_str = ", ".join(exclude_oils)
        custom_oils_block += f"\nМасла которые ЗАПРЕЩЕНО использовать: {exclude_str}"
        custom_oils_require += (
            f"\n- ЗАПРЕЩЕНО использовать масла: {exclude_str} "
            f"— не включай их ни в каком виде"
            f"\n- Подбери СОВЕРШЕННО ДРУГИЕ масла, не повторяй предыдущий состав"
        )

    prompt = _CONSTRUCT_BLEND_PROMPT.format(
        brief=brief,
        effects=", ".join(effects) if effects else "не указаны",
        speed=_SPEED_LABELS.get(speed, speed),
        application=_APP_LABELS.get(application, application),
        contraindications=contraindications or "нет",
        reference_context=reference_context[:2000],
        custom_oils_block=custom_oils_block,
        custom_oils_require=custom_oils_require,
    )

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        model=SONNET,
        context="blend_constructor/expert",
    )

    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(raw[start:end])
    raise ValueError("Failed to parse blend expert response")


async def verify_card_content(card: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Verify aromatherapy KB card content.

    Args:
        card: Card dict from get_reference_card or _serialize_model.
        dry_run: If True, only run rule-based checks (no LLM call).

    Returns:
        {"passed": bool, "score": float, "issues": list[str], "corrections": dict}
    """
    score, issues, corrections = _basic_verify(card)

    if dry_run:
        return {
            "passed": score >= 0.7,
            "score": score,
            "issues": issues,
            "corrections": corrections,
        }

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("ANTHROPIC_API_KEY not set — skipping LLM verification, using rule-based only")
        return {
            "passed": score >= 0.7,
            "score": score,
            "issues": issues,
            "corrections": corrections,
        }

    try:
        from bot.services.claude_client import call_claude

        card_summary = {
            "name": card.get("name"),
            "source_type": card.get("source_type"),
            "parent_group": card.get("parent_group"),
            "category_group": card.get("category_group"),
            "description_short": (str(card.get("description_short") or ""))[:200],
            "therapeutic_properties": (str(card.get("therapeutic_properties") or ""))[:300],
            "applications": (str(card.get("applications") or ""))[:200],
            "precautions": (str(card.get("precautions") or ""))[:200],
            "complementary_oil_names": (card.get("complementary_oil_names") or [])[:5],
        }

        from bot.services.claude_client import call_claude
        raw = call_claude(
            messages=[
                {
                    "role": "user",
                    "content": f"Верифицируй карточку:\n{json.dumps(card_summary, ensure_ascii=False, indent=2)}",
                }
            ],
            max_tokens=512,
            system=_EXPERT_SYSTEM_PROMPT,
            context="aromatherapy_expert",
        )
        # Extract JSON from response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(raw[start:end])
            # Merge with rule-based score (take minimum)
            llm_score = float(result.get("score", 1.0))
            final_score = round(min(score, llm_score), 2)
            all_issues = issues + list(result.get("issues") or [])
            all_corrections = {**corrections, **(result.get("corrections") or {})}
            return {
                "passed": final_score >= 0.7 and not any("wrong" in i.lower() for i in all_issues),
                "score": final_score,
                "issues": all_issues,
                "corrections": all_corrections,
            }
    except Exception as e:
        logger.warning("LLM verification failed: %s", e)

    # Fallback to rule-based
    return {
        "passed": score >= 0.7,
        "score": score,
        "issues": issues,
        "corrections": corrections,
    }
