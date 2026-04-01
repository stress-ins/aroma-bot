"""B-Roll Director — generates a detailed B-Roll Map from a YouTube script.

Parses [B-ROLL: ...] markers from the scenario and enriches them with
stock search keywords, camera motion, and mood annotations.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from bot.services.claude_client import call_claude
from bot.utils.json_parser import extract_json

logger = logging.getLogger(__name__)

from bot.agents.prompts.youtube_prompts import BROLL_DIRECTOR_PROMPT


@dataclass
class BRollCue:
    """A single B-Roll insertion point."""
    section_name: str           # which section it belongs to
    timestamp: str              # approximate start time, e.g. "1:45"
    duration: float             # seconds (3-5)
    description: str            # detailed visual description (Russian)
    source_type: str            # stock_photo | stock_video | generated_image
    search_keywords: list[str]  # English keywords for stock search
    camera_motion: str          # slow_zoom_in | pan_left | pan_right | static | parallax | slow_zoom_out
    mood: str                   # calm | dynamic | educational | warm | mysterious


def _parse_broll_map(raw: str) -> list[BRollCue]:
    """Parse B-Roll map. Tries JSON first, falls back to text markers."""
    try:
        items = extract_json(raw, expect_array=True)
        if isinstance(items, list):
            cues = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    dur = float(item.get("duration", 4.0))
                except (ValueError, TypeError):
                    dur = 4.0
                kw = item.get("search_keywords", [])
                if isinstance(kw, str):
                    kw = [k.strip() for k in kw.split(",") if k.strip()]
                cues.append(BRollCue(
                    section_name=item.get("section", ""),
                    timestamp=item.get("timestamp", ""),
                    duration=min(max(dur, 2.0), 8.0),
                    description=item.get("description", ""),
                    source_type=item.get("source_type", "stock_photo"),
                    search_keywords=kw[:5],
                    camera_motion=item.get("camera_motion", "slow_zoom_in"),
                    mood=item.get("mood", "calm"),
                ))
            if cues:
                return cues
    except (ValueError, TypeError):
        logger.debug("_parse_broll_map: JSON failed, using legacy parser")

    return _parse_broll_map_legacy(raw)


def _parse_broll_map_legacy(raw: str) -> list[BRollCue]:
    """Legacy parser: BROLL_N:/SECTION:/TIMESTAMP:/etc markers."""
    cues: list[BRollCue] = []

    blocks = re.split(r'(?=^BROLL_\d+:)', raw, flags=re.MULTILINE)
    for block in blocks:
        block = block.strip()
        if not block.startswith("BROLL_"):
            continue

        section = timestamp = description = source_type = camera = mood_val = ""
        duration = 4.0
        keywords: list[str] = []

        for line in block.splitlines():
            clean = line.strip().replace("**", "").strip()
            if clean.startswith("SECTION:"):
                section = clean[len("SECTION:"):].strip()
            elif clean.startswith("TIMESTAMP:"):
                timestamp = clean[len("TIMESTAMP:"):].strip()
            elif clean.startswith("DURATION:"):
                try:
                    duration = float(clean[len("DURATION:"):].strip())
                except ValueError:
                    duration = 4.0
            elif clean.startswith("DESCRIPTION:"):
                description = clean[len("DESCRIPTION:"):].strip()
            elif clean.startswith("SOURCE_TYPE:"):
                source_type = clean[len("SOURCE_TYPE:"):].strip()
            elif clean.startswith("SEARCH_KEYWORDS:"):
                kw_text = clean[len("SEARCH_KEYWORDS:"):].strip()
                keywords = [k.strip() for k in kw_text.split(",") if k.strip()]
            elif clean.startswith("CAMERA_MOTION:"):
                camera = clean[len("CAMERA_MOTION:"):].strip()
            elif clean.startswith("MOOD:"):
                mood_val = clean[len("MOOD:"):].strip()

        if description or section:
            cues.append(BRollCue(
                section_name=section,
                timestamp=timestamp,
                duration=min(max(duration, 2.0), 8.0),
                description=description,
                source_type=source_type or "stock_photo",
                search_keywords=keywords[:5],
                camera_motion=camera or "slow_zoom_in",
                mood=mood_val or "calm",
            ))

    return cues


def extract_broll_from_sections(sections: list[dict]) -> list[BRollCue]:
    """Quick extraction: pull B-Roll cues directly from parsed sections.

    This is a lightweight alternative to calling Claude — uses the broll_cue
    field already present in each section.
    """
    cues: list[BRollCue] = []
    for section in sections:
        cue_text = section.get("broll_cue", "").strip()
        if not cue_text:
            continue
        cues.append(BRollCue(
            section_name=section.get("section_type", ""),
            timestamp=section.get("timecode", "").split("–")[0].strip() if "–" in section.get("timecode", "") else "",
            duration=4.0,
            description=cue_text,
            source_type="stock_photo",
            search_keywords=[],
            camera_motion="slow_zoom_in",
            mood="calm",
        ))
    return cues


def generate_broll_map_sync(scenario_text: str) -> list[BRollCue]:
    """Call Claude to generate a detailed B-Roll Map from a YouTube script.

    Returns enriched BRollCue list with stock keywords and camera directions.
    """
    prompt = BROLL_DIRECTOR_PROMPT.format(scenario=scenario_text[:6000])

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=3000,
        context="broll director",
    )

    cues = _parse_broll_map(raw)
    if not cues:
        logger.warning("B-Roll Director returned 0 cues, raw preview: %s", raw[:500])
    else:
        logger.info("B-Roll Director generated %d cues", len(cues))

    return cues


def broll_map_to_payload(cues: list[BRollCue]) -> list[dict]:
    """Convert BRollCue list to JSON-serializable format for DraftModel.payload."""
    return [
        {
            "section_name": c.section_name,
            "timestamp": c.timestamp,
            "duration": c.duration,
            "description": c.description,
            "source_type": c.source_type,
            "search_keywords": c.search_keywords,
            "camera_motion": c.camera_motion,
            "mood": c.mood,
            "image_url": "",       # filled later when image is generated/selected
            "image_status": "pending",
        }
        for c in cues
    ]
