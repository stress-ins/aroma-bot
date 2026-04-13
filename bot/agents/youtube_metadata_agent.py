"""YouTube Metadata Agent — generates title, description with timecodes, tags.

Runs AFTER final montage, when real TTS segment durations are known.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from bot.agents.prompts.youtube_prompts import METADATA_PROMPT
from bot.services.claude_client import call_claude
from bot.utils.json_parser import extract_json

logger = logging.getLogger(__name__)


@dataclass
class YouTubeMetadata:
    """YouTube video metadata ready for upload."""
    title: str
    description: str
    tags: list[str]
    category_id: int
    chapters: list[dict]  # [{"time": 0, "title": "Intro"}, ...]


def _fmt_timecode(seconds: float) -> str:
    """Format seconds as H:MM:SS or M:SS."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_timecodes_block(sections_with_durations: list[dict]) -> str:
    """Build a timecodes block from sections with real durations.

    Each entry: {"label": "...", "start_seconds": float}
    """
    lines = []
    for sec in sections_with_durations:
        tc = _fmt_timecode(sec["start_seconds"])
        lines.append(f"{tc} — {sec['label']}")
    return "\n".join(lines)


def _parse_metadata(raw: str) -> YouTubeMetadata:
    """Parse metadata. Tries JSON first, falls back to text markers."""
    try:
        data = extract_json(raw)
        if isinstance(data, dict) and data.get("title"):
            tags = data.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            try:
                cat_id = int(data.get("category_id", 26))
            except (ValueError, TypeError):
                cat_id = 26
            chapters = []
            for ch in data.get("chapters", []):
                if isinstance(ch, dict):
                    try:
                        chapters.append({"time": int(ch.get("time", 0)), "title": ch.get("title", "")})
                    except (ValueError, TypeError):
                        pass
            return YouTubeMetadata(
                title=data["title"],
                description=data.get("description", ""),
                tags=tags[:30],
                category_id=cat_id,
                chapters=chapters,
            )
    except (ValueError, TypeError):
        logger.debug("_parse_metadata: JSON failed, using legacy parser")

    return _parse_metadata_legacy(raw)


def _parse_metadata_legacy(raw: str) -> YouTubeMetadata:
    """Legacy parser: TITLE:/DESCRIPTION:/TAGS:/CATEGORY: markers."""
    title = ""
    description_lines: list[str] = []
    tags: list[str] = []
    category_id = 26
    in_description = False

    for line in raw.splitlines():
        clean = line.strip().replace("**", "").strip()

        if clean.startswith("TITLE:"):
            title = clean[len("TITLE:"):].strip()
            in_description = False
        elif clean.startswith("DESCRIPTION:") or clean == "DESCRIPTION":
            in_description = True
            tail = clean[len("DESCRIPTION:"):].strip() if ":" in clean else ""
            if tail:
                description_lines.append(tail)
        elif clean.startswith("TAGS:"):
            in_description = False
            tags_text = clean[len("TAGS:"):].strip()
            tags = [t.strip() for t in tags_text.split(",") if t.strip()]
        elif clean.startswith("CATEGORY:"):
            in_description = False
            try:
                category_id = int(re.search(r'\d+', clean).group())
            except (AttributeError, ValueError):
                category_id = 26
        elif in_description:
            description_lines.append(line)

    description = "\n".join(description_lines).strip()

    chapters: list[dict] = []
    for match in re.finditer(r'(\d+:\d{2}(?::\d{2})?)\s*[—–-]\s*(.+)', description):
        tc_str = match.group(1)
        chapter_title = match.group(2).strip()
        parts = tc_str.split(":")
        if len(parts) == 3:
            seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            seconds = int(parts[0]) * 60 + int(parts[1])
        chapters.append({"time": seconds, "title": chapter_title})

    return YouTubeMetadata(
        title=title,
        description=description,
        tags=tags[:30],
        category_id=category_id,
        chapters=chapters,
    )


def generate_youtube_metadata_sync(
    scenario_text: str,
    sections_with_durations: list[dict],
    total_duration: float,
) -> YouTubeMetadata:
    """Generate YouTube metadata from scenario and real timecodes.

    Args:
        scenario_text: The full script text (will be truncated for prompt).
        sections_with_durations: List of dicts with 'label' and 'start_seconds'.
        total_duration: Total video duration in seconds.
    """
    timecodes_block = build_timecodes_block(sections_with_durations)

    prompt = METADATA_PROMPT.format(
        scenario_preview=scenario_text[:3000],
        timecodes_block=timecodes_block,
        total_duration=_fmt_timecode(total_duration),
    )

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        context="youtube metadata",
    )

    metadata = _parse_metadata(raw)
    logger.info(
        "YouTube metadata generated: title=%r, %d tags, %d chapters",
        metadata.title, len(metadata.tags), len(metadata.chapters),
    )
    return metadata


def metadata_to_payload(meta: YouTubeMetadata) -> dict:
    """Convert YouTubeMetadata to JSON-serializable dict."""
    return {
        "title": meta.title,
        "description": meta.description,
        "tags": meta.tags,
        "category_id": meta.category_id,
        "chapters": meta.chapters,
    }
