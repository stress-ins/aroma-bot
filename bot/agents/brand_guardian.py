"""Brand Guardian Agent — unified brand voice audit before publishing."""
from __future__ import annotations

import json
import logging
import re

from bot.agents.platform_rules import get_brand_context
from bot.services.brand_settings_store import get_brand_settings_cached

logger = logging.getLogger(__name__)

_SYSTEM = """\
{brand_context}

Ты — Brand Guardian. Твоя задача: проверить текст перед публикацией на соответствие \
голосу бренда и правилам площадки.

Проверяй по следующим критериям:

1. МЕДИЦИНСКИЕ УТВЕРЖДЕНИЯ
   Запрещено: утверждать лечебные свойства напрямую ("лечит", "исцеляет", "вылечит", \
   "устраняет болезнь", "избавит от заболевания").
   Допустимо: "может помочь", "традиционно используется", "многие отмечают", \
   "поддерживает состояние".

2. AI-ШТАМПЫ
   Запрещено: "в мире ароматерапии", "погрузитесь", "откройте для себя", \
   "удивительный мир", "невероятный", "поистине", "безусловно", \
   литературные метафоры ("плечи в камне", "мысли вязнут", "тело как свинец").

3. ЗАПРЕЩЁННЫЕ ФРАЗЫ БРЕНДА
   {forbidden_phrases}

4. ТОНАЛЬНОСТЬ
   Правильно: тёплый эксперт, живая речь, образовательный тон.
   Неправильно: продажный тон, агрессивный маркетинг, инфоцыганство, \
   пафос, слоганы, псевдопоэзия.

5. ПРАВИЛА ПЛОЩАДКИ ({platform})
   {platform_rules}

Верни СТРОГО валидный JSON (без markdown-обёртки, без ```json):
{{
  "passed": true/false,
  "score": 0.0-1.0,
  "violations": [
    {{"type": "medical_claim|ai_stamp|forbidden_phrase|tone|platform_rule", \
"detail": "описание", "severity": "error|warning"}}
  ],
  "suggested_fixes": ["конкретное исправление 1", ...],
  "cleaned_text": "исправленный текст (если есть нарушения) или оригинал"
}}

Правила оценки score:
- 1.0: идеальный текст, нет замечаний
- 0.8-0.9: мелкие замечания (warnings)
- 0.5-0.7: есть нарушения, требуются правки
- ниже 0.5: серьёзные нарушения (медицинские утверждения, грубые AI-штампы)

passed=true если score >= 0.8 и нет violations с severity="error".
"""

_PLATFORM_RULES = {
    "threads_series": "Серия из 3 постов, каждый до 500 символов. Без хэштегов.",
    "instagram": "До 900 символов (без хэштегов). Хэштеги в конце, 5-10 штук.",
    "telegram": "До 1200 символов. Без хэштегов. Можно **bold** для 1-2 фраз.",
    "default": "Короткий пост для соцсетей.",
}


def _build_system_prompt(platform: str) -> str:
    bs = get_brand_settings_cached()
    forbidden_block = ""
    if bs and bs.forbidden_phrases:
        forbidden_block = "\n".join(f'   - "{p}"' for p in bs.forbidden_phrases)
    else:
        forbidden_block = "   (не заданы)"

    platform_rules = _PLATFORM_RULES.get(platform, _PLATFORM_RULES["default"])

    return _SYSTEM.format(
        brand_context=get_brand_context(),
        forbidden_phrases=forbidden_block,
        platform=platform,
        platform_rules=platform_rules,
    )


def _parse_response(raw: str) -> dict:
    """Parse JSON from Claude response, handling possible markdown wrapping."""
    text = raw.strip()
    # Strip markdown code fence if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Brand Guardian: failed to parse JSON response: %s", text[:200])
        return {
            "passed": True,
            "score": 0.5,
            "violations": [],
            "suggested_fixes": [],
            "cleaned_text": "",
        }


def audit_brand_sync(text: str, platform: str, brand_context: str = "") -> dict:
    """Audit text for brand voice compliance.

    Returns {
        "passed": bool,
        "score": float,  # 0.0 to 1.0
        "violations": [{"type": str, "detail": str, "severity": "error"|"warning"}],
        "suggested_fixes": [str],
        "cleaned_text": str  # text with fixes applied
    }
    """
    from bot.services.claude_client import call_claude

    system_prompt = _build_system_prompt(platform)
    if brand_context:
        system_prompt = brand_context + "\n\n" + system_prompt

    result = call_claude(
        messages=[{"role": "user", "content": f"Проверь этот текст:\n\n{text}"}],
        max_tokens=1200,
        system=system_prompt,
        context="brand guardian",
    )

    parsed = _parse_response(result)

    # Ensure required fields
    parsed.setdefault("passed", True)
    parsed.setdefault("score", 0.5)
    parsed.setdefault("violations", [])
    parsed.setdefault("suggested_fixes", [])
    parsed.setdefault("cleaned_text", text)

    # If cleaned_text is empty, fall back to original
    if not parsed["cleaned_text"]:
        parsed["cleaned_text"] = text

    return parsed
