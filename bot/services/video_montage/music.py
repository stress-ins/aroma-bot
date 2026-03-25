"""Background music mixing and beat detection."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Built-in royalty-free music library (paths relative to project root)
MUSIC_LIBRARY = {
    "calm_ambient": "assets/music/calm_ambient.mp3",
    "warm_acoustic": "assets/music/warm_acoustic.mp3",
    "gentle_piano": "assets/music/gentle_piano.mp3",
    "energetic_beat": "assets/music/energetic_beat.mp3",
    "mysterious_pad": "assets/music/mysterious_pad.mp3",
}

MUSIC_LABELS = {
    "calm_ambient": "Спокойный эмбиент",
    "warm_acoustic": "Тёплая акустика",
    "gentle_piano": "Мягкое пианино",
    "energetic_beat": "Энергичный бит",
    "mysterious_pad": "Таинственный пад",
}


def build_music_filter(
    music_path: str,
    video_duration: float,
    volume: float = 0.15,
    fade_in: float = 2.0,
    fade_out: float = 3.0,
) -> tuple[list[str], str]:
    """Build FFmpeg args for mixing background music.

    Returns:
        (extra_input_args, audio_filter_string)
        extra_input_args: ["-i", "music.mp3"] to add as second input
        audio_filter_string: amix filter to combine speech + music
    """
    if not Path(music_path).exists():
        logger.warning("Music file not found: %s", music_path)
        return [], ""

    extra_inputs = ["-i", music_path]

    # Music: loop if shorter than video, trim to video length, apply volume + fades
    fade_out_start = max(0, video_duration - fade_out)
    music_filter = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=duration={video_duration:.1f},"
        f"volume={volume:.2f},"
        f"afade=t=in:st=0:d={fade_in:.1f},"
        f"afade=t=out:st={fade_out_start:.1f}:d={fade_out:.1f}[music];"
        f"[0:a][music]amix=inputs=2:duration=shortest[aout]"
    )

    return extra_inputs, music_filter


def detect_beats(music_path: str) -> list[float]:
    """Detect beat timestamps in music file using FFmpeg.

    Returns list of timestamps (seconds) where beats occur.
    Uses FFmpeg's `astats` and energy-based detection.
    """
    if not Path(music_path).exists():
        return []

    # Use FFmpeg to get audio energy at intervals
    cmd = [
        "ffmpeg", "-i", music_path,
        "-af", "silencedetect=noise=-30dB:d=0.1",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # Parse silence end times as approximate beat positions
    beats: list[float] = []
    for line in result.stderr.split("\n"):
        if "silence_end:" in line:
            try:
                ts = float(line.split("silence_end:")[1].split("|")[0].strip())
                beats.append(ts)
            except (ValueError, IndexError):
                logger.warning("detect_beats: float failed", exc_info=True)
                pass

    logger.info("Detected %d beats in %s", len(beats), music_path)
    return beats


def snap_to_beats(
    cut_times: list[float],
    beats: list[float],
    tolerance: float = 0.3,
) -> list[float]:
    """Snap cut timestamps to nearest beats within tolerance.

    Returns adjusted cut times.
    """
    if not beats:
        return cut_times

    adjusted = []
    for cut in cut_times:
        nearest = min(beats, key=lambda b: abs(b - cut))
        if abs(nearest - cut) <= tolerance:
            adjusted.append(nearest)
        else:
            adjusted.append(cut)
    return adjusted
