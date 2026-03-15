"""Humanizer — post-processing module to remove AI artifacts from generated text."""
from __future__ import annotations

import logging
import re
from collections import Counter

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
