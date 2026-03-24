"""Apply FFmpeg video filters for color correction."""
from __future__ import annotations

import asyncio
import logging
import subprocess

from bot.services.video_grader.config import GradeResult, GraderConfig

logger = logging.getLogger(__name__)


class FFmpegGradeError(RuntimeError):
    def __init__(self, command: str, stderr: str):
        self.command = command
        self.stderr = stderr
        super().__init__(f"FFmpeg failed: {stderr[:300]}")


def _get_duration(filepath: str) -> float:
    """Get video duration via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def apply_grade(
    config: GraderConfig,
    vf_string: str,
    output_file: str = "",
) -> GradeResult:
    """Apply FFmpeg video filter chain to input video."""
    if not output_file:
        from pathlib import Path
        p = Path(config.input_file)
        output_file = str(p.with_stem(p.stem + "_graded"))

    cmd = [
        "ffmpeg",
        "-i", config.input_file,
        "-vf", vf_string,
        "-c:v", config.video_codec,
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", config.audio_codec,
        "-y", output_file,
    ]

    cmd_str = " ".join(cmd)
    logger.debug("Running FFmpeg: %s", cmd_str)

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600,
    )

    if result.returncode != 0:
        raise FFmpegGradeError(cmd_str, result.stderr)

    input_dur = _get_duration(config.input_file)
    output_dur = _get_duration(output_file)

    return GradeResult(
        success=True,
        output_file=output_file,
        input_duration=input_dur,
        output_duration=output_dur,
        ffmpeg_command=cmd_str,
        stderr=result.stderr,
    )


def apply_partial_grade(
    config: GraderConfig,
    filters: list[str],
    output_file: str = "",
) -> GradeResult:
    """Apply selected filters only."""
    vf_string = ",".join(f for f in filters if f.strip())
    if not vf_string:
        raise ValueError("No filters to apply")
    return apply_grade(config, vf_string, output_file)


async def apply_grade_async(
    config: GraderConfig,
    vf_string: str,
    output_file: str = "",
) -> GradeResult:
    """Async wrapper."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: apply_grade(config, vf_string, output_file)
    )
