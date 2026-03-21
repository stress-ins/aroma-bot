"""Split mode orchestrator — group intervals into clips and render."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from bot.services.video_processor.config import ProcessorConfig
from bot.services.video_processor.filter_engine import Interval

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    """Raised when FFmpeg returns a non-zero exit code."""

    def __init__(self, cmd: list[str], returncode: int, stderr: str) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"FFmpeg failed (rc={returncode}): {stderr[:500]}")


def group_intervals_into_clips(
    intervals: list[Interval],
    config: ProcessorConfig,
) -> list[list[Interval]]:
    """Group keep-intervals into clips respecting max/min duration limits.

    Uses a greedy approach: accumulate intervals until adding another would
    exceed ``split_max_clip_duration``, then start a new clip.  If the last
    clip is too short, merge it into the previous one.
    """
    if not intervals:
        return []

    clips: list[list[Interval]] = [[]]
    clip_duration = 0.0

    for iv in intervals:
        iv_dur = iv.duration
        if clip_duration + iv_dur > config.split_max_clip_duration and clips[-1]:
            clips.append([])
            clip_duration = 0.0
        clips[-1].append(iv)
        clip_duration += iv_dur

    # Merge orphan last clip into previous if too short
    if len(clips) > 1:
        last_dur = sum(iv.duration for iv in clips[-1])
        if last_dur < config.split_min_clip_duration:
            clips[-2].extend(clips.pop())

    return clips


def run_split(
    input_file: Path,
    clips: list[list[Interval]],
    output_dir: Path,
    config: ProcessorConfig,
) -> list[Path]:
    """Render each clip group using FFmpeg.

    For single-interval clips: simple ``-ss``/``-to`` seek.
    For multi-interval clips: trim + concat filter.

    Returns list of output file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_files: list[Path] = []

    for i, clip_intervals in enumerate(clips):
        total_dur = sum(iv.duration for iv in clip_intervals)
        if total_dur < config.split_min_clip_duration:
            logger.debug("Skipping clip %d (%.2fs < min)", i + 1, total_dur)
            continue

        filename = config.split_naming_pattern.format(i + 1)
        out_path = output_dir / filename

        logger.info(
            "[%d/%d] Rendering %s (%.1fs — %.1fs)...",
            i + 1, len(clips), filename,
            clip_intervals[0].start, clip_intervals[-1].end,
        )

        if len(clip_intervals) == 1:
            iv = clip_intervals[0]
            cmd = [
                "ffmpeg", "-y",
                "-i", str(input_file),
                "-ss", f"{iv.start:.3f}",
                "-to", f"{iv.end:.3f}",
                "-c:v", config.video_codec,
                "-preset", config.preset,
                "-crf", str(config.crf),
                "-c:a", config.audio_codec,
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(out_path),
            ]
        else:
            # Multi-interval clip: trim + concat
            n = len(clip_intervals)
            parts: list[str] = []
            for j, iv in enumerate(clip_intervals):
                parts.append(
                    f"[0:v]trim=start={iv.start:.3f}:end={iv.end:.3f},"
                    f"setpts=PTS-STARTPTS[v{j}]",
                )
                parts.append(
                    f"[0:a]atrim=start={iv.start:.3f}:end={iv.end:.3f},"
                    f"asetpts=PTS-STARTPTS[a{j}]",
                )
            v_inputs = "".join(f"[v{j}][a{j}]" for j in range(n))
            parts.append(f"{v_inputs}concat=n={n}:v=1:a=1[outv][outa]")

            cmd = [
                "ffmpeg", "-y",
                "-i", str(input_file),
                "-filter_complex", ";".join(parts),
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", config.video_codec,
                "-preset", config.preset,
                "-crf", str(config.crf),
                "-c:a", config.audio_codec,
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(out_path),
            ]

        _run_ffmpeg(cmd)
        output_files.append(out_path)

    return output_files


def _run_ffmpeg(cmd: list[str]) -> None:
    """Execute an FFmpeg command, raising ``FFmpegError`` on failure."""
    logger.debug("FFmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise FFmpegError(cmd, result.returncode, result.stderr)
