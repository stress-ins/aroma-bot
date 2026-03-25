"""Content Coach Agent — AI-powered analysis of published post performance."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

# ── System prompts ──────────────────────────────────────────────────────────

_ANALYZE_SYSTEM = """\
Ты — опытный контент-стратег и аналитик для специалиста по ароматерапии, \
звукотерапии и регуляции нервной системы через сенсорные практики.

Твоя задача — объяснить ПОЧЕМУ конкретный пост сработал хорошо или плохо, \
сравнивая его с бенчмарками команды.

Правила:
- Анализируй на русском языке
- Будь конкретным: не "текст плохой", а "слишком длинный абзац 2 теряет внимание после 3-й строки"
- Сравнивай с бенчмарками — показывай отклонения в процентах
- Давай actionable советы — что конкретно изменить
- Если есть caption — анализируй его структуру (хук, тело, CTA)
- Учитывай формат (carousel vs reels vs text) при анализе

Отвечай ТОЛЬКО валидным JSON без markdown-обёрток и пояснений.
"""

_ANALYZE_USER = """\
Проанализируй эффективность опубликованного поста.

ПОСТ:
- Платформа: {platform}
- Формат: {kind}
- Тема: {topic}
- Контент-столп: {content_pillar}
- Этап воронки: {funnel_stage}
- Метрики: лайки={likes}, комментарии={comments}, репосты={shares}, сохранения={saves}, просмотры={views}
- Оценки: вовлечение={score_engagement}/5, бренд={score_brand_fit}/5, контент={score_craft}/5, цель={score_goal_hit}/5

{caption_block}

БЕНЧМАРКИ КОМАНДЫ:
- Средние оценки: вовлечение={avg_engagement}, бренд={avg_brand}, контент={avg_craft}, цель={avg_goal}
- Средняя общая оценка: {avg_total}

БЕНЧМАРКИ ФОРМАТА ({kind}):
- Средняя оценка формата: {format_avg}
- Количество публикаций формата: {format_count}

БЕНЧМАРКИ СТОЛПА ({content_pillar}):
- Средняя оценка столпа: {pillar_avg}
- Количество публикаций столпа: {pillar_count}

Верни JSON:
{{
  "verdict": "success" | "average" | "underperformed",
  "score_vs_average": <число — процент отклонения от средней команды, например +23.5 или -15.0>,
  "strengths": ["конкретная сильная сторона 1", "конкретная сильная сторона 2"],
  "weaknesses": ["конкретная слабость 1", "конкретная слабость 2"],
  "recommendations": ["конкретная рекомендация 1", "конкретная рекомендация 2"],
  "score_explanation": {{
    "engagement": "объяснение оценки вовлечения относительно среднего",
    "brand_fit": "объяснение оценки бренда",
    "craft": "объяснение оценки контента",
    "goal_hit": "объяснение оценки попадания в цель"
  }},
  "patterns_detected": ["паттерн 1", "паттерн 2"],
  "suggested_improvements": "Переписанный вариант caption или конкретные правки"
}}
"""

_SUMMARY_SYSTEM = """\
Ты — контент-стратег, который анализирует портфель публикаций команды \
и даёт стратегические рекомендации.

Тематика: ароматерапия, звукотерапия, регуляция нервной системы, сенсорные практики.

Правила:
- Анализируй на русском языке
- Опирайся на данные — показывай конкретные цифры
- Давай actionable рекомендации на ближайшую неделю
- Выявляй паттерны: какие форматы и темы работают лучше
- Указывай пробелы в контенте

Отвечай ТОЛЬКО валидным JSON без markdown-обёрток и пояснений.
"""

_SUMMARY_USER = """\
Проанализируй портфель публикаций команды и дай стратегические рекомендации.

ПУБЛИКАЦИИ ({pub_count} шт.):
{publications_summary}

ЭФФЕКТИВНОСТЬ ПО ФОРМАТАМ:
{format_summary}

ЭФФЕКТИВНОСТЬ ПО СТОЛПАМ КОНТЕНТА:
{pillar_summary}

Верни JSON:
{{
  "top_insight": "главный инсайт одним предложением",
  "format_recommendations": [
    {{"format": "название формата", "verdict": "keep|improve|experiment|drop", "note": "пояснение"}}
  ],
  "pillar_recommendations": [
    {{"pillar": "название столпа", "verdict": "scale|keep|experiment|drop", "note": "пояснение"}}
  ],
  "content_gaps": ["пробел в контенте 1", "пробел 2"],
  "weekly_plan_suggestion": "рекомендация на неделю"
}}
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict | None:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Content Coach: failed to parse JSON: %s", text[:300])
        return None


def _safe_avg(scores: list[float | int | None]) -> float:
    """Average of non-None values, or 0."""
    valid = [s for s in scores if s is not None]
    return round(sum(valid) / len(valid), 1) if valid else 0.0


def _find_benchmark(benchmarks: list[dict], key_field: str, key_value: str) -> dict:
    """Find a benchmark dict by key field value."""
    for b in benchmarks:
        if b.get(key_field) == key_value:
            return b
    return {}


# ── Fallbacks ────────────────────────────────────────────────────────────────

_ANALYZE_FALLBACK: dict = {
    "verdict": "average",
    "score_vs_average": 0.0,
    "strengths": [],
    "weaknesses": [],
    "recommendations": ["Недостаточно данных для детального анализа"],
    "score_explanation": {
        "engagement": "Нет данных",
        "brand_fit": "Нет данных",
        "craft": "Нет данных",
        "goal_hit": "Нет данных",
    },
    "patterns_detected": [],
    "suggested_improvements": "",
}

_SUMMARY_FALLBACK: dict = {
    "top_insight": "Недостаточно данных для анализа. Добавьте больше публикаций с оценками.",
    "format_recommendations": [],
    "pillar_recommendations": [],
    "content_gaps": [],
    "weekly_plan_suggestion": "Начните с добавления и оценки публикаций в архив.",
}


# ── Core functions ───────────────────────────────────────────────────────────

def _analyze_sync(
    post: dict,
    team_averages: dict,
    format_benchmarks: list[dict],
    pillar_benchmarks: list[dict],
) -> dict:
    """Synchronous LLM call for post analysis."""
    from bot.services.claude_client import call_claude

    # Find matching format/pillar benchmarks
    fmt_bench = _find_benchmark(format_benchmarks, "kind", post.get("kind", ""))
    pil_bench = _find_benchmark(pillar_benchmarks, "pillar", post.get("content_pillar", ""))

    caption_block = ""
    if post.get("caption"):
        caption_block = f"ТЕКСТ ПОСТА:\n---\n{post['caption'][:2000]}\n---"

    user_prompt = _ANALYZE_USER.format(
        platform=post.get("platform", "unknown"),
        kind=post.get("kind", "unknown"),
        topic=post.get("topic", "Без темы"),
        content_pillar=post.get("content_pillar", "не указан"),
        funnel_stage=post.get("funnel_stage", "не указан"),
        likes=post.get("likes", 0),
        comments=post.get("comments", 0),
        shares=post.get("shares", 0),
        saves=post.get("saves", 0),
        views=post.get("views", 0),
        score_engagement=post.get("score_engagement", "н/д"),
        score_brand_fit=post.get("score_brand_fit", "н/д"),
        score_craft=post.get("score_craft", "н/д"),
        score_goal_hit=post.get("score_goal_hit", "н/д"),
        caption_block=caption_block,
        avg_engagement=team_averages.get("avg_engagement", "н/д"),
        avg_brand=team_averages.get("avg_brand", "н/д"),
        avg_craft=team_averages.get("avg_craft", "н/д"),
        avg_goal=team_averages.get("avg_goal", "н/д"),
        avg_total=team_averages.get("avg_total", "н/д"),
        format_avg=fmt_bench.get("avg_score", "н/д"),
        format_count=fmt_bench.get("count", 0),
        pillar_avg=pil_bench.get("avg_score", "н/д"),
        pillar_count=pil_bench.get("count", 0),
    )

    raw = call_claude(
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=1500,
        system=_ANALYZE_SYSTEM,
        context="content_coach_analyze",
    )

    parsed = _parse_json(raw)
    if parsed is None:
        return dict(_ANALYZE_FALLBACK)

    # Validate and set defaults
    if parsed.get("verdict") not in ("success", "average", "underperformed"):
        parsed["verdict"] = "average"

    try:
        parsed["score_vs_average"] = float(parsed.get("score_vs_average", 0))
    except (TypeError, ValueError):
        parsed["score_vs_average"] = 0.0

    parsed.setdefault("strengths", [])
    parsed.setdefault("weaknesses", [])
    parsed.setdefault("recommendations", [])
    parsed.setdefault("score_explanation", _ANALYZE_FALLBACK["score_explanation"])
    parsed.setdefault("patterns_detected", [])
    parsed.setdefault("suggested_improvements", "")

    return parsed


def _summary_sync(
    publications: list[dict],
    format_performance: list[dict],
    pillar_performance: list[dict],
) -> dict:
    """Synchronous LLM call for coaching summary."""
    from bot.services.claude_client import call_claude

    # Build concise publication summary
    pub_lines = []
    for p in publications[:30]:  # Limit to 30 for context window
        score = _safe_avg([
            p.get("score_engagement"),
            p.get("score_brand_fit"),
            p.get("score_craft"),
            p.get("score_goal_hit"),
        ])
        pub_lines.append(
            f"- [{p.get('kind', '?')}] {p.get('topic', 'Без темы')[:60]} "
            f"({p.get('platform', '?')}) — {score}★, "
            f"likes={p.get('likes', 0)}, views={p.get('views', 0)}"
        )

    format_lines = []
    for f in format_performance:
        format_lines.append(f"- {f['kind']}: ø {f['avg_score']}★ ({f['count']} публ.)")

    pillar_lines = []
    for pl in pillar_performance:
        pillar_lines.append(f"- {pl['pillar']}: ø {pl['avg_score']}★ ({pl['count']} публ.)")

    user_prompt = _SUMMARY_USER.format(
        pub_count=len(publications),
        publications_summary="\n".join(pub_lines) or "Нет данных",
        format_summary="\n".join(format_lines) or "Нет данных",
        pillar_summary="\n".join(pillar_lines) or "Нет данных",
    )

    raw = call_claude(
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=1200,
        system=_SUMMARY_SYSTEM,
        context="content_coach_summary",
    )

    parsed = _parse_json(raw)
    if parsed is None:
        return dict(_SUMMARY_FALLBACK)

    # Validate
    parsed.setdefault("top_insight", _SUMMARY_FALLBACK["top_insight"])
    parsed.setdefault("format_recommendations", [])
    parsed.setdefault("pillar_recommendations", [])
    parsed.setdefault("content_gaps", [])
    parsed.setdefault("weekly_plan_suggestion", "")

    return parsed


# ── Public async API ─────────────────────────────────────────────────────────

async def analyze_post_performance(
    post: dict,
    team_averages: dict,
    format_benchmarks: list[dict],
    pillar_benchmarks: list[dict],
) -> dict:
    """Analyze why a published post performed well or poorly.

    Args:
        post: PastPublicationRecord data as dict
        team_averages: Average scores across all team's posts
        format_benchmarks: from content_analytics.get_format_performance()
        pillar_benchmarks: from content_analytics.get_pillar_performance()

    Returns:
        {
            "verdict": "success" | "average" | "underperformed",
            "score_vs_average": float,
            "strengths": [...],
            "weaknesses": [...],
            "recommendations": [...],
            "score_explanation": {"engagement": ..., "brand_fit": ..., "craft": ..., "goal_hit": ...},
            "patterns_detected": [...],
            "suggested_improvements": str,
        }
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _analyze_sync, post, team_averages, format_benchmarks, pillar_benchmarks,
    )


async def generate_coaching_summary(
    publications: list[dict],
    format_performance: list[dict],
    pillar_performance: list[dict],
) -> dict:
    """Generate overall coaching summary from all team publications.

    Returns:
        {
            "top_insight": str,
            "format_recommendations": [...],
            "pillar_recommendations": [...],
            "content_gaps": [...],
            "weekly_plan_suggestion": str,
        }
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _summary_sync, publications, format_performance, pillar_performance,
    )
