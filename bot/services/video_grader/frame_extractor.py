"""Extract reference frames from video using FFmpeg."""
from __future__ import annotations

import asyncio
import logging
import struct
import subprocess
from pathlib import Path

from bot.services.video_grader.config import FrameInfo, GraderConfig

logger = logging.getLogger(__name__)


class FrameExtractionError(RuntimeError):
    pass


def _get_duration(input_file: str) -> float:
    """Get video duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise FrameExtractionError(f"ffprobe failed: {result.stderr[:200]}")
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise FrameExtractionError(f"Could not parse duration: {result.stdout[:100]}")


def _compute_brightness(frame_path: str) -> float:
    """Compute average brightness of a frame (0.0–1.0)."""
    cmd = [
        "ffmpeg", "-i", frame_path,
        "-vf", "scale=64:64,format=gray",
        "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "gray",
        "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=15)
    if result.returncode != 0 or not result.stdout:
        return 0.5
    pixels = result.stdout
    avg = sum(pixels) / len(pixels) if pixels else 128
    return round(avg / 255.0, 3)


def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _extract_single_frame(
    input_file: str, timestamp: float, output_path: str, quality: int = 90,
) -> None:
    """Extract a single frame at given timestamp."""
    cmd = [
        "ffmpeg", "-ss", str(timestamp),
        "-i", input_file,
        "-vframes", "1",
        "-q:v", str(max(1, min(31, (100 - quality) * 31 // 100 + 1))),
        "-y", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise FrameExtractionError(
            f"Failed to extract frame at {timestamp}s: {result.stderr[:200]}"
        )


def extract_frames(config: GraderConfig) -> list[FrameInfo]:
    """Extract reference frames from video according to config strategy."""
    input_file = config.input_file
    if not Path(input_file).exists():
        raise FrameExtractionError(f"Input file not found: {input_file}")

    duration = _get_duration(input_file)
    if duration <= 0:
        raise FrameExtractionError(f"Invalid video duration: {duration}")

    # Prepare output directory
    output_dir = Path(config.frame_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Clean old frames
    for old in output_dir.glob(f"frame_*.{config.frame_format}"):
        old.unlink()

    # Compute timestamps
    if config.frame_strategy == "manual" and config.frame_timestamps:
        timestamps = [(t, "manual") for t in config.frame_timestamps[:config.frame_count]]
    elif config.frame_strategy == "uniform":
        step = duration / (config.frame_count + 1)
        timestamps = [(step * (i + 1), "mid") for i in range(config.frame_count)]
    else:
        # smart strategy
        points = [0.05, 0.30, 0.50, 0.70, 0.90]
        types = ["intro", "mid", "mid", "mid", "outro"]
        timestamps = [
            (duration * p, t) for p, t in zip(points, types)
        ]
        # Trim to frame_count - 1 (reserve one for brightest)
        timestamps = timestamps[: config.frame_count - 1]

    # Extract frames
    frames: list[FrameInfo] = []
    for i, (ts, scene_type) in enumerate(timestamps):
        ts = min(ts, max(0, duration - 0.5))
        filename = f"frame_{i:02d}.{config.frame_format}"
        filepath = str(output_dir / filename)

        _extract_single_frame(input_file, ts, filepath, config.frame_quality)
        brightness = _compute_brightness(filepath)

        frames.append(FrameInfo(
            index=i,
            timestamp=round(ts, 2),
            timestamp_str=_format_timestamp(ts),
            filepath=filepath,
            scene_type=scene_type,
            brightness=brightness,
        ))

    # Smart: find brightest frame if we have room
    if config.frame_strategy == "smart" and len(frames) < config.frame_count:
        brightest = max(frames, key=lambda f: f.brightness) if frames else None
        if brightest and brightest.brightness > 0.6:
            # Already captured — add a dark frame instead
            darkest_ts = duration * 0.15
            idx = len(frames)
            filename = f"frame_{idx:02d}.{config.frame_format}"
            filepath = str(output_dir / filename)
            _extract_single_frame(input_file, darkest_ts, filepath, config.frame_quality)
            brightness = _compute_brightness(filepath)
            frames.append(FrameInfo(
                index=idx,
                timestamp=round(darkest_ts, 2),
                timestamp_str=_format_timestamp(darkest_ts),
                filepath=filepath,
                scene_type="bright",
                brightness=brightness,
            ))

    logger.info("Extracted %d frames from %s (%.1fs)", len(frames), input_file, duration)
    return frames


async def extract_frames_async(config: GraderConfig) -> list[FrameInfo]:
    """Async wrapper around extract_frames."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, extract_frames, config)
