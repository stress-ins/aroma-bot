"""Transcription layer — Whisper STT or FFmpeg silencedetect."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from bot.services.video_processor.config import ProcessorConfig

logger = logging.getLogger(__name__)


@dataclass
class WordTimestamp:
    """A single word with its time boundaries."""

    word: str
    start: float
    end: float


@dataclass
class SilenceInterval:
    """A detected silence region."""

    start: float
    end: float


def transcribe_whisper(input_file: Path, config: ProcessorConfig) -> list[WordTimestamp]:
    """Run Whisper STT and return word-level timestamps.

    Raises ``ImportError`` if whisper/torch are not installed.
    """
    import whisper  # noqa: WPS433 — lazy import

    logger.info(
        "Loading Whisper model '%s' (language=%s)...",
        config.whisper_model,
        config.whisper_language,
    )
    model = whisper.load_model(config.whisper_model)
    result = model.transcribe(
        str(input_file),
        language=config.whisper_language,
        word_timestamps=True,
    )

    words: list[WordTimestamp] = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            words.append(
                WordTimestamp(
                    word=w["word"].strip(),
                    start=w["start"],
                    end=w["end"],
                ),
            )

    logger.info("Whisper: extracted %d words", len(words))
    return words


def detect_silence(input_file: Path, config: ProcessorConfig) -> list[SilenceInterval]:
    """Run FFmpeg silencedetect and return silence intervals."""
    cmd = [
        "ffmpeg", "-i", str(input_file),
        "-af", f"silencedetect=noise={config.silence_threshold_db}dB:d={config.min_pause_duration}",
        "-f", "null", "-",
    ]
    logger.debug("silencedetect cmd: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    output = result.stderr  # silencedetect writes to stderr

    silence_starts: list[float] = []
    silence_ends: list[float] = []

    for line in output.splitlines():
        m_start = re.search(r"silence_start:\s*([\d.]+)", line)
        if m_start:
            silence_starts.append(float(m_start.group(1)))

        m_end = re.search(r"silence_end:\s*([\d.]+)", line)
        if m_end:
            silence_ends.append(float(m_end.group(1)))

    intervals: list[SilenceInterval] = []
    for i in range(min(len(silence_starts), len(silence_ends))):
        intervals.append(SilenceInterval(start=silence_starts[i], end=silence_ends[i]))

    # Handle trailing silence (start without matching end)
    if len(silence_starts) > len(silence_ends):
        duration = get_video_duration(input_file)
        if duration:
            intervals.append(
                SilenceInterval(start=silence_starts[-1], end=duration),
            )

    logger.info("silencedetect: found %d silence intervals", len(intervals))
    return intervals


def get_video_duration(input_file: Path) -> float | None:
    """Get video duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_file),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as exc:
        logger.warning("ffprobe duration failed: %s", exc)
    return None
