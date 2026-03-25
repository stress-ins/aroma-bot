"""YouTube Script Agent — generates scripts for long-form YouTube videos.

Supports three subformats:
- talking_head: single speaker, 5-15 min
- listicle: top-N list, 8-15 min
- podcast: interview/podcast with guest, 20-40 min
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from bot.agents.content import _HUMAN_WRITING_RULES
from bot.agents.reels_agent import EMOTION_LABELS, GOAL_LABELS
from bot.services.brand_settings_store import get_brand_settings_cached
from bot.services.claude_client import call_claude
from bot.services.humanizer import humanize

logger = logging.getLogger(__name__)

from bot.agents.prompts.youtube_prompts import (
    LISTICLE_PROMPT,
    PODCAST_PROMPT,
    TALKING_HEAD_PROMPT,
    TOPICS_PROMPT,
    _YOUTUBE_SHARED_RULES,
)

_REFERENCE_CONTEXT_MAX_CHARS = 3000  # longer than reels — more room for context


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

SUBFORMAT_LABELS: dict[str, str] = {
    "talking_head": "Talking Head (один спикер)",
    "listicle": "Listicle / Top-N (список)",
    "podcast": "Подкаст / Интервью (два спикера)",
}

DURATION_PRESETS: dict[str, dict] = {
    "talking_head": {"min": 5, "max": 15, "default": 10},
    "listicle": {"min": 8, "max": 15, "default": 10},
    "podcast": {"min": 20, "max": 40, "default": 30},
}


@dataclass
class YouTubeSection:
    """A single section of a YouTube script."""
    section_type: str       # HOOK, INTRO, MAIN_1, ITEM_1, QUESTION_1, RECAP, CTA, etc.
    label: str              # human-readable label
    timecode: str           # "0:00–1:30"
    speaker_text: str       # full speaker text (or host_text for podcast)
    screen_text: str        # overlay text for editing
    energy: str             # low / medium / medium-high / high
    broll_cue: str          # B-ROLL description from scenario
    # Podcast-specific
    guest_talking_points: list[str] = field(default_factory=list)
    follow_up: str = ""
    host_text: str = ""


@dataclass
class YouTubeScript:
    """Complete YouTube video script."""
    title: str
    subformat: str                      # talking_head | listicle | podcast
    sections: list[YouTubeSection]
    music_mood: str
    duration_target: int                # minutes
    # Podcast-specific
    guest_name: str = ""
    guest_expertise: str = ""
    # Raw text for reference
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _clean_line(line: str) -> str:
    """Strip markdown bold/heading markers."""
    return line.strip().lstrip("#").strip().replace("**", "").strip()


def _parse_youtube_script(raw: str, subformat: str) -> YouTubeScript:
    """Parse structured Claude response into YouTubeScript."""
    title = ""
    music_mood = ""
    guest_name = ""
    guest_expertise = ""
    sections: list[YouTubeSection] = []

    # Extract top-level fields
    for line in raw.splitlines():
        clean = _clean_line(line)
        if clean.startswith("TITLE:"):
            title = clean[len("TITLE:"):].strip()
        elif clean.startswith("MUSIC_MOOD:") or clean.startswith("MUSIC MOOD:"):
            music_mood = clean.split(":", 1)[1].strip()
        elif clean.startswith("GUEST_NAME:"):
            guest_name = clean[len("GUEST_NAME:"):].strip()
        elif clean.startswith("GUEST_EXPERTISE:"):
            guest_expertise = clean[len("GUEST_EXPERTISE:"):].strip()

    # Parse sections
    section_blocks = re.split(r'(?=^SECTION:\s)', raw, flags=re.MULTILINE)
    for block in section_blocks:
        block = block.strip()
        if not block.startswith("SECTION:"):
            continue

        section_type = label = timecode = speaker_text = screen_text = energy = ""
        broll_cue = host_text = follow_up = ""
        guest_points: list[str] = []
        in_guest_points = False
        in_questions = False
        questions: list[str] = []

        for line in block.splitlines():
            clean = _clean_line(line)

            if clean.startswith("SECTION:"):
                section_type = clean[len("SECTION:"):].strip()
                in_guest_points = False
                in_questions = False
            elif clean.startswith("TIMECODE:"):
                timecode = clean[len("TIMECODE:"):].strip()
            elif clean.startswith("LABEL:"):
                label = clean[len("LABEL:"):].strip()
            elif clean.startswith("SPEAKER_TEXT:"):
                speaker_text = clean[len("SPEAKER_TEXT:"):].strip()
                in_guest_points = False
            elif clean.startswith("HOST_TEXT:"):
                host_text = clean[len("HOST_TEXT:"):].strip()
                in_guest_points = False
            elif clean.startswith("SCREEN_TEXT:"):
                screen_text = clean[len("SCREEN_TEXT:"):].strip()
                in_guest_points = False
            elif clean.startswith("ENERGY:"):
                energy = clean[len("ENERGY:"):].strip()
                in_guest_points = False
            elif clean.startswith("FOLLOW_UP:"):
                follow_up = clean[len("FOLLOW_UP:"):].strip()
                in_guest_points = False
            elif clean.startswith("GUEST_TALKING_POINTS:"):
                in_guest_points = True
                in_questions = False
            elif clean.startswith("QUESTIONS:"):
                in_questions = True
                in_guest_points = False
            elif clean.startswith("[B-ROLL:"):
                broll_cue = clean.strip("[]").replace("B-ROLL:", "").strip()
                in_guest_points = False
            elif in_guest_points and clean.startswith("- "):
                guest_points.append(clean[2:].strip())
            elif in_questions and clean.startswith("- "):
                questions.append(clean[2:].strip())

        # For lightning round, combine questions into speaker_text
        if questions and not speaker_text:
            speaker_text = host_text
            if questions:
                speaker_text += "\n" + "\n".join(f"- {q}" for q in questions)

        if section_type:
            sections.append(YouTubeSection(
                section_type=section_type,
                label=label or section_type.replace("_", " ").title(),
                timecode=timecode,
                speaker_text=speaker_text or host_text,
                screen_text=screen_text,
                energy=energy,
                broll_cue=broll_cue,
                guest_talking_points=guest_points,
                follow_up=follow_up,
                host_text=host_text,
            ))

    return YouTubeScript(
        title=title,
        subformat=subformat,
        sections=sections,
        music_mood=music_mood,
        duration_target=0,
        guest_name=guest_name,
        guest_expertise=guest_expertise,
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# Timecode helpers for prompt generation
# ---------------------------------------------------------------------------

def _compute_section_timecodes(duration_minutes: int, subformat: str) -> dict[str, str]:
    """Compute approximate section timecode boundaries for prompt placeholders."""
    total_sec = duration_minutes * 60

    if subformat == "talking_head":
        # Hook(30s) + Intro(60s) + 3 mains + Recap(30s) + CTA(30s)
        fixed = 30 + 60 + 30 + 30  # 150s
        main_total = total_sec - fixed
        main_each = max(60, main_total // 3)
        s1_end = 90 + main_each
        s2_end = s1_end + main_each
        s3_end = s2_end + main_each
        recap_end = s3_end + 30
        return {
            "section_end_1": _fmt_time(s1_end),
            "section_end_2": _fmt_time(s2_end),
            "section_end_3": _fmt_time(s3_end),
            "recap_end": _fmt_time(recap_end),
            "total_end": _fmt_time(total_sec),
        }
    return {}


def _fmt_time(seconds: int) -> str:
    """Format seconds as M:SS."""
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _render_reference_context_block(reference_context: str) -> str:
    text = str(reference_context or "").strip()
    if not text:
        return ""
    bounded = text[:_REFERENCE_CONTEXT_MAX_CHARS].rstrip()
    return (
        "\nДанные из нашего справочника (используй для точности описаний и формулировок):\n"
        + bounded
        + "\n"
    )


def generate_youtube_topics_sync(
    trends_text: str,
    subformat: str = "talking_head",
    duration_target: int = 10,
) -> list[str]:
    """Generate 7 YouTube video topic suggestions."""
    bs = get_brand_settings_cached()
    subformat_label = SUBFORMAT_LABELS.get(subformat, subformat)
    duration_label = f"~{duration_target} мин"

    prompt = TOPICS_PROMPT.format(
        brand_context=bs.brand_voice,
        trends_text=trends_text,
        subformat_label=subformat_label,
        duration_label=duration_label,
    )

    text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=700,
        context="youtube topics",
    )

    topics: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            topics.append(line.split(". ", 1)[1].strip())
    return topics[:7]


def generate_youtube_script_sync(
    topic: str,
    subformat: str = "talking_head",
    goal: str = "trust",
    emotion: str = "calm",
    duration_target: int = 10,
    reference_context: str = "",
    *,
    item_count: int = 7,
    question_count: int = 6,
    guest_description: str = "",
) -> YouTubeScript:
    """Generate a complete YouTube script for the given subformat."""
    bs = get_brand_settings_cached()
    forbidden_block = (
        "НЕ использовать следующие фразы:\n"
        + "\n".join(f"- {p}" for p in bs.forbidden_phrases)
        if bs.forbidden_phrases
        else ""
    )
    goal_label = GOAL_LABELS.get(goal, goal)
    emotion_label = EMOTION_LABELS.get(emotion, emotion)
    ref_block = _render_reference_context_block(reference_context)

    if subformat == "talking_head":
        tc = _compute_section_timecodes(duration_target, subformat)
        prompt = TALKING_HEAD_PROMPT.format(
            brand_context=bs.brand_voice,
            reference_context_block=ref_block,
            topic=topic,
            goal_label=goal_label,
            emotion_label=emotion_label,
            duration_target=duration_target,
            forbidden_block=forbidden_block,
            human_writing_rules=_HUMAN_WRITING_RULES,
            _youtube_shared_rules=_YOUTUBE_SHARED_RULES,
            **tc,
        )
        max_tokens = 3000
    elif subformat == "listicle":
        prompt = LISTICLE_PROMPT.format(
            brand_context=bs.brand_voice,
            reference_context_block=ref_block,
            topic=topic,
            goal_label=goal_label,
            emotion_label=emotion_label,
            duration_target=duration_target,
            item_count=item_count,
            forbidden_block=forbidden_block,
            human_writing_rules=_HUMAN_WRITING_RULES,
            _youtube_shared_rules=_YOUTUBE_SHARED_RULES,
        )
        max_tokens = 4000
    elif subformat == "podcast":
        prompt = PODCAST_PROMPT.format(
            brand_context=bs.brand_voice,
            reference_context_block=ref_block,
            topic=topic,
            goal_label=goal_label,
            emotion_label=emotion_label,
            duration_target=duration_target,
            question_count=question_count,
            guest_description=guest_description or "не указан — предложи подходящего эксперта",
            forbidden_block=forbidden_block,
            human_writing_rules=_HUMAN_WRITING_RULES,
            _youtube_shared_rules=_YOUTUBE_SHARED_RULES,
        )
        max_tokens = 5000
    else:
        raise ValueError(f"Unknown subformat: {subformat!r}")

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        context=f"youtube script ({subformat})",
    )
    raw = humanize(raw)

    script = _parse_youtube_script(raw, subformat)
    script.duration_target = duration_target
    return script


def script_to_payload(script: YouTubeScript) -> dict:
    """Convert a YouTubeScript to a JSON-serializable dict for DraftModel.payload."""
    return {
        "title": script.title,
        "subformat": script.subformat,
        "duration_target": script.duration_target,
        "music_mood": script.music_mood,
        "guest_name": script.guest_name,
        "guest_expertise": script.guest_expertise,
        "sections": [
            {
                "section_type": s.section_type,
                "label": s.label,
                "timecode": s.timecode,
                "speaker_text": s.speaker_text,
                "screen_text": s.screen_text,
                "energy": s.energy,
                "broll_cue": s.broll_cue,
                "guest_talking_points": s.guest_talking_points,
                "follow_up": s.follow_up,
                "host_text": s.host_text,
            }
            for s in script.sections
        ],
    }
