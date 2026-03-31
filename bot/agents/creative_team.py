from __future__ import annotations

from bot.agents.platform_rules import (
    EDITOR_PLATFORM_RULES,
    HUMAN_WRITING_RULES,
    get_brand_context,
)
from bot.services.brand_settings_store import get_brand_settings_cached
from bot.services.humanizer import humanize, humanize_llm
from bot.services.policy_engine import enforce_policy

import logging

logger = logging.getLogger(__name__)


_EDITOR_SYSTEM = """\
{brand_context}

Ты — главред с 10-летним опытом редактуры контента для Instagram и Threads \
в нишах wellbeing, психология, образ жизни.

Главное правило: пиши как живой человек говорит с другим живым человеком. \
Не как лектор, не как коуч на вебинаре — как подруга, которая хорошо разбирается в теме.

Правила редактуры:
1. Первая строка — останавливает скролл. Провокация, факт, признание, вопрос без \
   ответа. Плохо: "В нашей работе есть важная деталь." \
   Хорошо: "Большинство корпоративных велнес-программ — это красивая бумажка."
2. Убери AI-штампы: "погружаясь в...", "исследуя...", "это то, что...", \
   "позволь себе...", "мощный инструмент", "невероятный результат".
3. Убери умные слова там, где можно сказать проще. \
   Плохо: "активация парасимпатической нервной системы", "интегрировать опыт", \
   "ресурсное состояние", "работать с телесными ощущениями". \
   Хорошо: "тело выдыхает", "стало чуть легче", "голова перестала гудеть".
4. Убери длинные вводные. Первое слово — сразу в суть.
5. Тело: конкретные ситуации из жизни вместо абстракций. Не "стресс влияет на нас", \
   а "ты лежишь и не можешь уснуть, хотя устал".
6. Не используй литературные метафоры, которые человек не говорит в обычной речи. \
   Плохо: "плечи в камне", "мысли вязнут", "тревога стекает по телу". \
   Хорошо: "плечи зажаты", "в голове шумно", "тело всё ещё напряжено".
7. Не пиши рублеными слоганами и псевдопоэтическими короткими фразами. \
   Плохо: "Минует логику. Говорит телу." \
   Хорошо: "Запах срабатывает быстрее, чем длинные объяснения, и тело это замечает почти сразу."
8. Если фраза звучит как копирайтерский слоган или красивая заготовка, перепиши её в живую разговорную речь.
9. Запрещённые слова и обороты:
{forbidden_phrases}
   Вместо "мы сжимаем живот" → "у нас часто напряжено тело, особенно в животе". \
   Вместо "просто стой" → "просто дыши" или "просто наблюдай".
10. Каждая фраза должна быть логически завершена. Никаких оборванных мыслей. \
    Плохо: "раскрыть женское", "это не романтика, это возможность чувствовать без стены". \
    Хорошо: дочитал — понял, о чём речь, и мысль закрыта.
11. CTA — человеческий, не рекламный. Как будто пишешь другу.
12. Не увеличивай длину. Лучше сократи.
13. Для Threads не схлопывай всё в один пост: сохрани три отдельных блока УТРО / ДЕНЬ / ВЕЧЕР. \
    Строки «Почему это сработает:» — аннотация для автора, не редактируй и не удаляй их.
14. Проверь логику соседних фраз. Одна фраза должна естественно продолжать предыдущую, а не звучать как случайный красивый тезис.
15. Не делай текст "с подвыподвертом": без вычурности, без насильственной глубины, без интонации "сейчас скажу умную вещь".
16. Не используй жёсткие, рубленые и неестественные конструкции ради эффекта. \
   Плохо: "Запах заходит в тело быстрее мысли.", "Нервная система не спорит. Она отвечает." \
   Хорошо: "Иногда запах срабатывает быстрее, чем ты успеваешь всё объяснить себе словами."
17. Если мысль можно сказать проще и теплее — скажи проще и теплее. Текст должен читаться так, будто человек написал его сам, а не выжал из себя формулировку.
18. Верни только отредактированный текст поста — ничего больше.

{human_writing_rules}
"""


def edit_post_sync(raw: str, topic: str, platform: str = "default", user_forbidden: list[str] | None = None) -> str:
    """Run an editor pass over a raw post. Returns the polished post text."""
    from bot.services.claude_client import call_claude

    platform_rule = EDITOR_PLATFORM_RULES.get(platform, EDITOR_PLATFORM_RULES["default"])
    user_msg = (
        f"\u0422\u0435\u043c\u0430 \u043f\u043e\u0441\u0442\u0430: {topic}\n"
        f"{platform_rule}\n\n"
        f"\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a:\n{raw}"
    )
    if user_forbidden:
        extra = "\n".join(f"- {p}" for p in user_forbidden)
        user_msg += f"\n\n\u0414\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u0437\u0430\u043f\u0440\u0435\u0449\u0451\u043d\u043d\u044b\u0435 \u0444\u0440\u0430\u0437\u044b (\u0443\u043a\u0430\u0437\u0430\u043d\u044b \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u043c):\n{extra}"

    bs = get_brand_settings_cached()
    forbidden_block = "\n".join(f'   "{p}",' for p in bs.forbidden_phrases) if bs.forbidden_phrases else ""
    system_prompt = _EDITOR_SYSTEM.format(
        brand_context=get_brand_context(),
        forbidden_phrases=forbidden_block,
        human_writing_rules=HUMAN_WRITING_RULES,
    )

    result = call_claude(
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=700,
        system=system_prompt,
        context=f"editor ({platform})",
    )
    # Fallback: if editor returns something too short, keep original
    result = result if len(result) > 30 else raw
    # Apply policy enforcement (soft rewrites + forbidden phrase detection)
    policy_result = enforce_policy(result, platform)
    cleaned = humanize(policy_result.text, platform)
    humanized = humanize_llm(cleaned, platform) if platform != "threads_series" else cleaned

    # Brand Guardian validation pass — blocking for severity=error violations
    from bot.agents.brand_guardian import audit_brand_sync

    try:
        audit = audit_brand_sync(humanized, platform)
        if not audit.get("passed", True):
            if audit.get("cleaned_text"):
                humanized = audit["cleaned_text"]
            else:
                # If there are error-level violations but no cleaned_text,
                # log a warning so the quality evaluator will catch it downstream
                errors = [v for v in audit.get("violations", []) if v.get("severity") == "error"]
                if errors:
                    logger.warning(
                        "Brand Guardian: %d error-level violations remain after edit: %s",
                        len(errors),
                        "; ".join(v.get("detail", "") for v in errors),
                    )
    except Exception:
        logger.warning("creative_team: brand guardian failed", exc_info=True)
        # On exception, still return the humanized text — don't break pipeline on infra errors

    return humanized


def _auto_apply_optimizations(
    text: str,
    optimization: dict,
    topic: str,
    platform: str,
) -> str:
    """Auto-apply high-impact suggestions from platform optimizer via LLM rewrite."""
    high_impact = [
        opt for opt in optimization.get("optimizations", [])
        if opt.get("impact") == "high" and opt.get("suggested")
    ]
    if not high_impact:
        return text

    from bot.services.claude_client import call_claude

    suggestions_block = "\n".join(
        f"- {opt['type']}: {opt['suggested']}" for opt in high_impact[:3]
    )
    prompt = (
        f"Перепиши текст поста, применив следующие оптимизации для алгоритма {platform}:\n"
        f"{suggestions_block}\n\n"
        f"Тема: {topic}\n\n"
        f"Текст:\n{text}\n\n"
        f"Правила:\n"
        f"- Сохрани основную мысль, тон и длину\n"
        f"- Примени указанные улучшения\n"
        f"- Верни ТОЛЬКО текст поста, без комментариев\n"
        f"- Без markdown-форматирования"
    )
    try:
        result = call_claude(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            context=f"optimizer auto-apply ({platform})",
        )
        result = result.strip()
        if len(result) > 30:
            logger.info("Auto-applied %d high-impact optimizations for %s", len(high_impact), platform)
            return result
    except Exception:
        logger.warning("_auto_apply_optimizations: LLM rewrite failed", exc_info=True)
    return text


def edit_post_with_optimization_sync(
    raw: str,
    topic: str,
    platform: str = "default",
    content_type: str = "post",
    user_forbidden: list[str] | None = None,
) -> dict:
    """Edit a post and augment with platform optimization suggestions.

    Returns {
        "text": str,  # the edited post text
        "platform_optimization": dict | None,  # optimization suggestions
    }
    """
    text = edit_post_sync(raw, topic, platform, user_forbidden)

    platform_optimization = None
    try:
        from bot.agents.platform_optimizer import optimize_for_platform_sync

        platform_optimization = optimize_for_platform_sync(
            text=text,
            platform=platform,
            content_type=content_type,
        )

        # Auto-apply high-impact suggestions from platform optimizer
        if platform_optimization:
            text = _auto_apply_optimizations(text, platform_optimization, topic, platform)
    except Exception:
        logger.warning("edit_post_with_optimization_sync: optimizer failed", exc_info=True)

    return {
        "text": text,
        "platform_optimization": platform_optimization,
    }

