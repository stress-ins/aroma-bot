"""B-roll insertion — splice AI-generated images between video segments."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def create_broll_clip(
    image_path: str,
    duration: float = 2.0,
    output_path: str = "",
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Convert a still image to a video clip with Ken Burns zoom effect.

    Returns path to the created clip.
    """
    if not output_path:
        output_path = str(Path(image_path).with_suffix(".mp4"))

    # Ken Burns: slow zoom in over duration
    vf = (
        f"scale={width * 2}:{height * 2},"
        f"zoompan=z='min(zoom+0.001,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={int(duration * 30)}:s={width}x{height}:fps=30"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        # Silent audio
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-shortest",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        logger.error("B-roll creation failed: %s", result.stderr[:200])
        return ""

    return output_path


def select_broll_positions(
    keep_intervals: list[list[float]],
    max_inserts: int = 3,
) -> list[int]:
    """Select best positions to insert B-roll between segments.

    Picks gaps where adjacent segments have the longest pause
    (natural break points for B-roll).

    Returns list of indices: insert B-roll AFTER segment[i].
    """
    if len(keep_intervals) < 3 or max_inserts <= 0:
        return []

    # Calculate gaps between segments
    gaps: list[tuple[float, int]] = []
    for i in range(len(keep_intervals) - 1):
        gap = keep_intervals[i + 1][0] - keep_intervals[i][1]
        gaps.append((gap, i))

    # Sort by gap size (largest first) and pick top N
    gaps.sort(reverse=True)
    positions = sorted([g[1] for g in gaps[:max_inserts]])

    return positions
