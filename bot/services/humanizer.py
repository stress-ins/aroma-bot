"""Humanizer — post-processing module to remove AI artifacts from generated text."""
from __future__ import annotations

import logging
import re
from collections import Counter
from textwrap import dedent

logger = logging.getLogger(__name__)

# Regex replacement rules applied in order
RULES: list[tuple[str, str]] = [
    (r'(\w)—(\w)', r'\1, \2'),      # word—word → word, word
    (r'\s—\s', ', '),                # space — space → comma
    (r'^—\s', ''),                   # leading em-dash on line start
    (r'\s–\s', ', '),                # en-dash with spaces → comma
    (r'(\w)–(\w)', r'\1-\2'),       # en-dash inside word → hyphen
    (r'\*\*(.+?)\*\*', r'\1'),      # **bold** → plain text
    (r'__(.+?)__', r'\1'),           # __bold__ → plain text
    (r'^\s*#{1,3}\s+', ''),          # ## Heading → plain text (per line)
    (r'`(.+?)`', r'\1'),             # `code` → plain text
    (r'\n{3,}', '\n\n'),             # 3+ blank lines → 2
    (r'[ \t]{2,}', ' '),             # multiple spaces → one
    (r'\.{4,}', '…'),               # .... → …
    (r'!{2,}', '!'),                 # !!! → !
    (r'\?{2,}', '?'),               # ??? → ?
    (r'^-{3,}\s*$', ''),             # --- separator → remove
    (r'^\*{3,}\s*$', ''),            # *** separator → remove
    (r'^_{3,}\s*$', ''),             # ___ separator → remove
]

# AI marker patterns for detection and logging
_AI_MARKERS: list[str] = [
    r'погружаясь в',
    r'исследуя',
    r'позволь себе',
    r'мощный инструмент',
    r'невероятный результат',
    r'важно отметить',
    r'следует сказать',
    r'\bданный\b',
    r'осуществляется',
    r'в рамках',
    r'активация парасимпатической',
    r'интегрировать опыт',
    r'ресурсное состояние',
    r'работать с телесными',
    r'это то, что',
    r'невероятно',
    r'поистине',
    r'безусловно',
    r'несомненно',
    r'необходимо отметить',
    r'следует подчеркнуть',
    r'таким образом,',
    r'в заключение',
    r'подводя итог',
    r'резюмируя',
    r'хотелось бы отметить',
    r'примечательно',
    r'как известно',
    r'нельзя не отметить',
    r'с точки зрения',
]

_compiled_ai_markers = [(re.compile(p, re.IGNORECASE), p) for p in _AI_MARKERS]
_compiled_rules = [(re.compile(p, re.MULTILINE), r) for p, r in RULES]

# Aggregated marker counter for periodic logging
_marker_counter: Counter[str] = Counter()
_call_count = 0


def clean_text(text: str) -> str:
    """Apply all RULES to remove AI/markdown artifacts from text."""
    for pattern, replacement in _compiled_rules:
        text = pattern.sub(replacement, text)
    return text.strip()


def detect_ai_markers(text: str) -> list[str]:
    """Return list of AI marker patterns found in text (for logging only)."""
    return [raw for pattern, raw in _compiled_ai_markers if pattern.search(text)]


def humanize(text: str, platform: str = "") -> str:
    """Clean text and log detected AI markers. Main post-processing entry point."""
    global _call_count
    result = clean_text(text)
    markers = detect_ai_markers(result)
    if markers:
        logger.debug("humanize[%s]: AI markers found: %s", platform or "—", markers)
        for m in markers:
            _marker_counter[m] += 1
    _call_count += 1
    if _call_count % 10 == 0:
        top5 = _marker_counter.most_common(5)
        if top5:
            logger.info("humanizer top-5 AI markers (last %d calls): %s", _call_count, top5)
    return result


# ---------------------------------------------------------------------------
# LLM-based humanizer pass (two-pass: rewrite → self-audit)
# ---------------------------------------------------------------------------

_HUMANIZER_LLM_SYSTEM = dedent("""\
Ты — редактор-человек. Твоя задача — переписать текст так, чтобы он звучал \
как написанный живым человеком, а не языковой моделью.

Вот 24 типичных AI-паттерна, которые нужно убрать:

1. Шаблонные связки: «Важно отметить», «Следует подчеркнуть», «Стоит сказать», \
   «Необходимо понимать», «Нельзя не отметить».
2. Избыточные усилители: «невероятно», «поистине», «безусловно», «несомненно», \
   «абсолютно», «исключительно».
3. Канцеляризмы: «осуществляется», «в рамках», «данный», «является», \
   «представляет собой».
4. Фальшивая эмпатия: «Мы все знаем, как это бывает», «Каждый из нас сталкивался».
5. Псевдонаучность: «активация парасимпатической нервной системы», \
   «нейропластичность мозга».
6. Коучинговые клише: «позволь себе», «ресурсное состояние», «интегрировать опыт», \
   «работать с телесными ощущениями».
7. Литературные метафоры, которых нет в живой речи: «плечи в камне», \
   «мысли вязнут», «тревога стекает по телу».
8. Рубленые слоганы: «Минует логику. Говорит телу.» — звучит как копирайтинг.
9. Списки с одинаковой структурой (параллелизм). Живые люди не пишут \
   5 пунктов с одинаковой грамматикой.
10. Избыточная структурированность: слишком аккуратные абзацы одной длины.
11. «В заключение», «Подводя итог», «Резюмируя» — AI-маркеры финала.
12. Восклицательные знаки для искусственного энтузиазма.
13. Повторение ключевого слова/темы в каждом абзаце (keyword stuffing).
14. Идеальная грамматика без единой разговорной конструкции.
15. Абстрактные утверждения без конкретных примеров из жизни.
16. Сложноподчинённые предложения длиной 3+ строки.
17. «Это не просто X, это Y» — шаблон контраста.
18. Перечисление через запятую 4+ синонимов подряд.
19. Начало абзаца с герундия: «Погружаясь в…», «Исследуя…».
20. Универсальные утверждения без оговорок: «всегда», «никогда», «каждый».
21. Избыточные хедж-фразы: «в определённом смысле», «в какой-то мере».
22. Пассивный залог там, где естественнее активный.
23. Формальные обращения в неформальном контексте.
24. Идеально симметричная структура «проблема → решение → результат».

Правила переписывания:
- Сохрани смысл, факты и CTA.
- Не добавляй новую информацию.
- Не увеличивай длину текста — лучше сократи.
- Пиши как живой человек говорит другу, который интересуется темой.
- Сохрани формат (абзацы, переносы строк).
- Верни ТОЛЬКО переписанный текст, без комментариев и пояснений.

После переписывания — проведи самоаудит: перечитай свой текст и проверь, \
не осталось ли в нём хотя бы одного из 24 паттернов выше. Если нашёл — \
исправь прямо в тексте. Верни финальный результат.
""")


def humanize_llm(text: str, platform: str = "") -> str:
    """Run an LLM pass to rewrite text in a more human style.

    Uses Haiku for speed and cost (~$0.001/call).
    Falls back to the original text on any error.
    """
    from bot.services.claude_client import call_claude

    if not text or len(text) < 40:
        return text

    try:
        result = call_claude(
            messages=[{"role": "user", "content": text}],
            max_tokens=1200,
            system=_HUMANIZER_LLM_SYSTEM,
            context=f"humanizer-llm ({platform})" if platform else "humanizer-llm",
        )
        # Sanity check: result should not be drastically shorter or empty
        if result and len(result) > len(text) * 0.3:
            return result
        logger.warning("humanize_llm: result too short (%d vs %d), keeping original", len(result), len(text))
        return text
    except Exception:
        logger.exception("humanize_llm: LLM call failed, keeping original text")
        return text
