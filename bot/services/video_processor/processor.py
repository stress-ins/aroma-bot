"""Main orchestrator — accepts config, runs the full pipeline."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from bot.services.video_processor.config import ProcessorConfig
from bot.services.video_processor.filter_engine import (
    Interval,
    build_keep_intervals_from_silence,
    build_keep_intervals_from_words,
)
from bot.services.video_processor.splitter import FFmpegError, group_intervals_into_clips, run_split
from bot.services.video_processor.transcriber import (
    WordTimestamp,
    detect_silence,
    get_video_duration,
    transcribe_whisper,
)

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """Result of a video processing run."""

    mode: str
    output_files: list[str]
    total_input_duration: float
    total_output_duration: float
    removed_duration: float
    clip_count: int
    whisper_segments: list[WordTimestamp] | None = None
    keep_intervals: list[tuple[float, float]] = field(default_factory=list)


def _format_duration(seconds: float) -> str:
    """Format seconds as 'Xm Ys'."""
    m, s = divmod(int(seconds), 60)
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def process(config: ProcessorConfig) -> ProcessResult:
    """Run the full video processing pipeline.

    1. Validate input & environment
    2. Detect silence / transcribe
    3. Build keep intervals
    4. Render output (single file or split clips)
    """
    input_file = Path(config.input_file)
    output_path = Path(config.output_path)

    # --- Validation ---
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg is not installed or not found in PATH. "
            "Install with: apt install ffmpeg (Ubuntu) or brew install ffmpeg (macOS)",
        )
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is not found in PATH (usually installed with ffmpeg)")

    # Probe duration
    total_duration = get_video_duration(input_file)
    if total_duration is None:
        raise RuntimeError(f"Could not determine duration of {input_file}")

    logger.info("Input: %s (%.1fs)", input_file.name, total_duration)

    # --- Transcription / silence detection ---
    whisper_words: list[WordTimestamp] | None = None
    intervals: list[Interval]

    if config.use_whisper:
        try:
            whisper_words = transcribe_whisper(input_file, config)
            intervals = build_keep_intervals_from_words(
                whisper_words, config, total_duration,
            )
        except ImportError:
            logger.warning(
                "Whisper not installed (pip install openai-whisper). "
                "Falling back to silencedetect.",
            )
            silence = detect_silence(input_file, config)
            intervals = build_keep_intervals_from_silence(
                silence, config, total_duration,
            )
        except (RuntimeError, MemoryError) as exc:
            logger.warning("Whisper failed (%s), falling back to silencedetect.", exc)
            silence = detect_silence(input_file, config)
            intervals = build_keep_intervals_from_silence(
                silence, config, total_duration,
            )
    else:
        silence = detect_silence(input_file, config)
        intervals = build_keep_intervals_from_silence(
            silence, config, total_duration,
        )

    if not intervals:
        raise ValueError(
            "No speech detected — the entire file appears to be silence. "
            "Try adjusting --silence-threshold or --min-pause-duration.",
        )

    output_duration = sum(iv.duration for iv in intervals)
    removed = total_duration - output_duration
    logger.info(
        "Found %d keep intervals, total: %s (removed %s)",
        len(intervals),
        _format_duration(output_duration),
        _format_duration(removed),
    )

    # --- Render ---
    output_path.mkdir(parents=True, exist_ok=True)
    output_files: list[str] = []

    if config.mode == "single":
        from bot.services.video_processor.ffmpeg_builder import build_single

        out_file = output_path / f"{input_file.stem}_clean.mp4"
        cmd = build_single(input_file, intervals, out_file, config)

        # Handle 2-pass demuxer concat (many segments)
        from bot.services.video_processor.ffmpeg_builder import _DemuxerCommand
        if isinstance(cmd, _DemuxerCommand) and cmd.pre_commands:
            logger.info("Using 2-pass concat demuxer (%d segments)", len(cmd.pre_commands))
            import shutil
            try:
                for i, pre_cmd in enumerate(cmd.pre_commands):
                    logger.debug("Extracting segment %d/%d", i + 1, len(cmd.pre_commands))
                    r = subprocess.run(pre_cmd, capture_output=True, text=True, timeout=60)
                    if r.returncode != 0:
                        raise FFmpegError(pre_cmd, r.returncode, r.stderr)
                # Pass 2: concat
                logger.debug("Concat pass: %s", " ".join(list(cmd)[:8]))
                result = subprocess.run(list(cmd), capture_output=True, text=True, timeout=600)
                if result.returncode != 0:
                    raise FFmpegError(list(cmd), result.returncode, result.stderr)
            finally:
                if cmd.tmp_dir:
                    shutil.rmtree(cmd.tmp_dir, ignore_errors=True)
        else:
            logger.debug("FFmpeg cmd: %s", " ".join(cmd)[:500])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise FFmpegError(cmd, result.returncode, result.stderr)

        if not out_file.exists() or out_file.stat().st_size == 0:
            raise RuntimeError("FFmpeg produced no output file")

        output_files = [str(out_file)]
        logger.info("Output: %s (%.1f MB)", out_file, out_file.stat().st_size / 1e6)

    elif config.mode == "split":
        clips = group_intervals_into_clips(intervals, config)
        files = run_split(input_file, clips, output_path, config)
        output_files = [str(f) for f in files]

    else:
        raise ValueError(f"Unknown mode: {config.mode!r}")

    # --- Result ---
    result_obj = ProcessResult(
        mode=config.mode,
        output_files=output_files,
        total_input_duration=total_duration,
        total_output_duration=output_duration,
        removed_duration=removed,
        clip_count=len(output_files),
        whisper_segments=whisper_words,
        keep_intervals=[(iv.start, iv.end) for iv in intervals],
    )

    logger.info(
        "Done. Input: %s -> Output: %s (removed %s of silence/fillers)",
        _format_duration(total_duration),
        _format_duration(output_duration),
        _format_duration(removed),
    )

    return result_obj
