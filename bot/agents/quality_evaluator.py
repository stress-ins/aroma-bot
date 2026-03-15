"""QualityEvaluator — scores generated content and provides critique for retry loops."""
from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


class ContentScore(TypedDict):
    hook_strength: float       # 0..1 — does the opening line stop the scroll?
    coherence: float           # 0..1 — logical flow, no contradictions
    cta_clarity: float         # 0..1 — clear next action for the reader
    brand_fit: float           # 0..1 — matches brand voice and constraints
    humanness: float           # 0..1 — reads like written by a human, not AI
    overall: float             # 0..1 — weighted average
    critique: str              # human-readable feedback for retry prompt
    passed: bool               # overall >= threshold (default 0.65)


_THRESHOLD = 0.65

_EVAL_SYSTEM = """\
Ты — строгий редактор контента для специалиста по регуляции нервной системы через сенсорные практики.
Твоя задача — объективно оценить качество текста по четырём критериям.
Отвечай ТОЛЬКО валидным JSON без пояснений и markdown.
"""

_EVAL_PROMPT_TEMPLATE = """\
Платформа: {platform}
Тема: {topic}

Текст:
---
{text}
---

Оцени текст по пяти критериям (каждый от 0.0 до 1.0):

1. hook_strength — первая строка останавливает скролл, конкретная, не банальная
2. coherence — текст логичен, мысли связаны, нет противоречий
3. cta_clarity — понятное следующее действие для читателя (или его отсутствие — ок для informational)
4. brand_fit — соответствует тону бренда: спокойный, живой, без псевдомедицины и инфоцыганства
5. humanness — текст звучит как написанный живым человеком:
   - нет длинных тире, нет нумерованных списков в теле поста
   - нет вводных AI-конструкций ("важно отметить", "следует сказать")
   - нет AI-канцелярита ("данный", "осуществляется", "в рамках")
   - ритм живой, предложения разной длины

Дополнительный контекст бренда:
- Основные темы: ароматерапия, медитации, гонг, звук, регуляция нервной системы
- Запрещено: обещать лечение, ставить диагнозы, "одна практика изменит всю жизнь"
- Язык: человеческий, не корпоративный, не эзотерический туман

Ответь строго в формате JSON:
{{
  "hook_strength": 0.0,
  "coherence": 0.0,
  "cta_clarity": 0.0,
  "brand_fit": 0.0,
  "humanness": 0.0,
  "critique": "Конкретный совет что улучшить (1-3 предложения на русском)"
}}
"""


def _call_claude(prompt: str, system: str = "") -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    kwargs: dict = dict(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text.strip()


def _evaluate_sync(text: str, platform: str, topic: str) -> ContentScore:
    prompt = _EVAL_PROMPT_TEMPLATE.format(
        platform=platform,
        topic=topic,
        text=text[:3000],
    )
    try:
        raw = _call_claude(prompt, system=_EVAL_SYSTEM)
        # Strip potential markdown code fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        hook = float(data.get("hook_strength", 0.5))
        coherence = float(data.get("coherence", 0.5))
        cta = float(data.get("cta_clarity", 0.5))
        brand = float(data.get("brand_fit", 0.5))
        humanness = float(data.get("humanness", 0.5))
        overall = round((hook * 0.25 + coherence * 0.20 + cta * 0.15 + brand * 0.20 + humanness * 0.20), 3)
        critique = str(data.get("critique", ""))
        return ContentScore(
            hook_strength=round(hook, 3),
            coherence=round(coherence, 3),
            cta_clarity=round(cta, 3),
            brand_fit=round(brand, 3),
            humanness=round(humanness, 3),
            overall=overall,
            critique=critique,
            passed=overall >= _THRESHOLD,
        )
    except Exception as exc:
        logger.warning("QualityEvaluator parse error: %s", exc)
        return ContentScore(
            hook_strength=0.5,
            coherence=0.5,
            cta_clarity=0.5,
            brand_fit=0.5,
            humanness=0.5,
            overall=0.5,
            critique=f"Ошибка оценки: {exc}",
            passed=False,
        )


async def evaluate_content(text: str, platform: str = "instagram", topic: str = "") -> ContentScore:
    """Score content quality. Returns ContentScore with .passed flag and .critique for retry."""
    if not settings.anthropic_api_key:
        # Graceful degradation when Claude not configured
        return ContentScore(
            hook_strength=0.7,
            coherence=0.7,
            cta_clarity=0.7,
            brand_fit=0.7,
            humanness=0.7,
            overall=0.7,
            critique="",
            passed=True,
        )
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _evaluate_sync, text, platform, topic)
