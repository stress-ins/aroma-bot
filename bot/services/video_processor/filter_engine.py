"""Build keep-intervals from transcription / silence detection results."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.services.video_processor.config import ProcessorConfig
from bot.services.video_processor.transcriber import SilenceInterval, WordTimestamp

logger = logging.getLogger(__name__)


@dataclass
class Interval:
    """A time range to keep in the output."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def _merge_overlapping(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping or adjacent intervals."""
    if not intervals:
        return []
    sorted_ivs = sorted(intervals, key=lambda iv: iv.start)
    merged = [Interval(start=sorted_ivs[0].start, end=sorted_ivs[0].end)]
    for iv in sorted_ivs[1:]:
        if iv.start <= merged[-1].end:
            merged[-1].end = max(merged[-1].end, iv.end)
        else:
            merged.append(Interval(start=iv.start, end=iv.end))
    return merged


def build_keep_intervals_from_words(
    words: list[WordTimestamp],
    config: ProcessorConfig,
    total_duration: float,
) -> list[Interval]:
    """Build keep intervals from Whisper word timestamps.

    1. Filter out filler words
    2. Group remaining words into segments (break on pauses > min_pause_duration)
    3. Apply padding
    4. Merge overlapping intervals
    """
    filler_set = {w.lower().strip() for w in config.filler_words}

    # Filter filler words
    kept_words = [w for w in words if w.word.lower().strip() not in filler_set]
    if not kept_words:
        return []

    removed = len(words) - len(kept_words)
    if removed:
        logger.info("Filtered %d filler words out of %d total", removed, len(words))

    # Group words into segments by pause gaps
    segments: list[Interval] = []
    seg_start = kept_words[0].start
    seg_end = kept_words[0].end

    for w in kept_words[1:]:
        gap = w.start - seg_end
        if gap > config.min_pause_duration:
            segments.append(Interval(
                start=max(0.0, seg_start - config.padding),
                end=min(total_duration, seg_end + config.padding),
            ))
            seg_start = w.start
        seg_end = w.end

    # Final segment
    segments.append(Interval(
        start=max(0.0, seg_start - config.padding),
        end=min(total_duration, seg_end + config.padding),
    ))

    return _merge_overlapping(segments)


def build_keep_intervals_from_silence(
    silence_intervals: list[SilenceInterval],
    config: ProcessorConfig,
    total_duration: float,
) -> list[Interval]:
    """Invert silence intervals to get speech (keep) intervals.

    1. Invert: gaps between silences = speech
    2. Apply padding
    3. Merge overlapping intervals
    """
    if not silence_intervals:
        # No silence found — keep everything
        return [Interval(start=0.0, end=total_duration)]

    # Sort by start time
    sorted_silences = sorted(silence_intervals, key=lambda s: s.start)

    speech: list[Interval] = []

    # Speech before first silence
    if sorted_silences[0].start > 0:
        speech.append(Interval(
            start=0.0,
            end=min(total_duration, sorted_silences[0].start + config.padding),
        ))

    # Speech between consecutive silences
    for i in range(len(sorted_silences) - 1):
        gap_start = sorted_silences[i].end
        gap_end = sorted_silences[i + 1].start
        if gap_end - gap_start > 0.01:  # skip negligible gaps
            speech.append(Interval(
                start=max(0.0, gap_start - config.padding),
                end=min(total_duration, gap_end + config.padding),
            ))

    # Speech after last silence
    if sorted_silences[-1].end < total_duration:
        speech.append(Interval(
            start=max(0.0, sorted_silences[-1].end - config.padding),
            end=total_duration,
        ))

    return _merge_overlapping(speech)
