"""Build FFmpeg filter for transitions between segments."""
from __future__ import annotations

import logging
from bot.services.video_montage.config import MontageConfig

logger = logging.getLogger(__name__)


def build_transition_filter(
    config: MontageConfig,
    segment_durations: list[float],
) -> str:
    """Build xfade filter chain for transitions between segments.

    Returns the -filter_complex string fragment for video transitions.
    If segments are too many (>30), uses simple crossfade approach.
    """
    n = len(segment_durations)
    if n <= 1:
        return ""

    xf_dur = min(config.transition_duration, 0.5)
    transition = config.transition_type
    if transition not in ("fade", "dissolve", "wipeleft", "slideright", "circlecrop"):
        transition = "fade"

    # For many segments, just use concat with brief crossfade
    if n > 30:
        logger.info("Too many segments (%d) for xfade, using simple concat", n)
        return ""

    parts: list[str] = []
    offset = segment_durations[0] - xf_dur

    for i in range(1, n):
        effective_xf = min(xf_dur, segment_durations[i] * 0.4)
        if effective_xf < 0.05:
            # Segment too short for transition
            offset += segment_durations[i]
            continue
        safe_offset = max(0.0, offset)
        in_label = f"xv{i - 1}" if i > 1 else "0:v"
        out_label = f"xv{i}" if i < n - 1 else "vout"
        parts.append(
            f"[{in_label}][{i}:v]xfade=transition={transition}"
            f":duration={effective_xf:.3f}:offset={safe_offset:.3f}[{out_label}]"
        )
        offset += segment_durations[i] - effective_xf

    return ";".join(parts)
