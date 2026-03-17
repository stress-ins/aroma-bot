"""Video composer — Ken Burns effect + crossfade transitions + text overlays via FFmpeg."""
from __future__ import annotations

import asyncio
import logging
import math
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

# Output specs (match reels_video.py constants)
OUT_WIDTH = 1080
OUT_HEIGHT = 1920
TARGET_RATIO = 9 / 16

# Ken Burns headroom: scale source to 120% so we can pan/zoom
KB_SCALE = 1.20
KB_WIDTH = int(OUT_WIDTH * KB_SCALE)   # 1296
KB_HEIGHT = int(OUT_HEIGHT * KB_SCALE)  # 2304

# Ensure even dimensions (required by H.264)
KB_WIDTH = KB_WIDTH + (KB_WIDTH % 2)
KB_HEIGHT = KB_HEIGHT + (KB_HEIGHT % 2)

DEFAULT_FRAME_DURATION = 7.5
DEFAULT_CROSSFADE = 0.5
DEFAULT_TOTAL_DURATION = 30.0
FPS = 30


async def check_ffmpeg_available() -> bool:
    """Check if ffmpeg is installed and accessible."""
    return shutil.which("ffmpeg") is not None


def _compute_durations(
    n_frames: int,
    durations: list[float] | None,
    total_duration: float,
    crossfade: float,
) -> list[float]:
    """Compute per-frame durations.

    If *durations* is provided, use those values directly.
    Otherwise distribute *total_duration* evenly across frames,
    accounting for crossfade overlap between adjacent frames.
    """
    if durations:
        if len(durations) < n_frames:
            last = durations[-1] if durations else DEFAULT_FRAME_DURATION
            durations = list(durations) + [last] * (n_frames - len(durations))
        return durations[:n_frames]

    if n_frames == 1:
        return [total_duration]

    # Total visible time = sum(durations) - (n-1)*crossfade = total_duration
    # => sum(durations) = total_duration + (n-1)*crossfade
    total_with_overlap = total_duration + (n_frames - 1) * crossfade
    per_frame = total_with_overlap / n_frames
    # Minimum 2 seconds per frame
    per_frame = max(per_frame, 2.0)
    return [per_frame] * n_frames


def _kb_filter(index: int, duration: float, fps: int = FPS) -> str:
    """Build a Ken Burns zoompan filter expression for a single frame.

    Alternates between 4 motion types:
    0 - zoom in (center)
    1 - pan left to right
    2 - zoom out (center)
    3 - pan right to left

    Uses the ``zoompan`` filter which is designed for Ken Burns effects.
    The source is already scaled to KB_WIDTH x KB_HEIGHT.
    zoompan outputs OUT_WIDTH x OUT_HEIGHT.
    """
    total_frames = int(math.ceil(duration * fps))
    motion = index % 4

    # zoom range: 1.0 means showing full KB image scaled to output,
    # KB_SCALE (1.2) means fully zoomed in so output = original OUT size
    z_min = 1.0
    z_max = KB_SCALE  # 1.2

    if motion == 0:
        # Zoom in: 1.0 -> 1.2
        z_expr = f"{z_min}+({z_max}-{z_min})*on/{total_frames}"
        x_expr = f"iw/2-(iw/zoom/2)"
        y_expr = f"ih/2-(ih/zoom/2)"
    elif motion == 1:
        # Pan left to right at mid-zoom
        z_mid = (z_min + z_max) / 2
        z_expr = f"{z_mid}"
        # x pans from 0 to max offset
        x_expr = f"(iw-iw/zoom)*on/{total_frames}"
        y_expr = f"ih/2-(ih/zoom/2)"
    elif motion == 2:
        # Zoom out: 1.2 -> 1.0
        z_expr = f"{z_max}-({z_max}-{z_min})*on/{total_frames}"
        x_expr = f"iw/2-(iw/zoom/2)"
        y_expr = f"ih/2-(ih/zoom/2)"
    else:
        # Pan right to left at mid-zoom
        z_mid = (z_min + z_max) / 2
        z_expr = f"{z_mid}"
        x_expr = f"(iw-iw/zoom)*(1-on/{total_frames})"
        y_expr = f"ih/2-(ih/zoom/2)"

    return (
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={total_frames}:s={OUT_WIDTH}x{OUT_HEIGHT}:fps={fps}"
    )


def _drawtext_filter(text: str, duration: float, fade_dur: float = 0.5) -> str:
    """Build a drawtext filter for overlay text on a frame."""
    escaped = text.replace("'", "\u2019").replace(":", "\\:")
    # Fade alpha: in for first fade_dur, out for last fade_dur
    alpha_expr = (
        f"if(lt(t\\,{fade_dur})\\,t/{fade_dur}\\,"
        f"if(gt(t\\,{duration - fade_dur})\\,({duration}-t)/{fade_dur}\\,1))"
    )
    return (
        f"drawtext=text='{escaped}'"
        f":fontsize=42"
        f":fontcolor=white"
        f":x=(w-text_w)/2"
        f":y=h-text_h-120"
        f":alpha={alpha_expr}"
        f":box=1:boxcolor=black@0.5:boxborderw=16"
    )


async def compose_video_from_frames(
    frame_paths: list[Path],
    durations: list[float] | None = None,
    overlay_texts: list[str] | None = None,
    output_path: Path | None = None,
    total_duration: float = DEFAULT_TOTAL_DURATION,
    crossfade: float = DEFAULT_CROSSFADE,
) -> Path:
    """Compose Ken Burns video from still images with transitions and text overlays.

    Returns path to the output MP4 file.

    Raises ``RuntimeError`` if FFmpeg is not installed or fails.
    """
    if not frame_paths:
        raise ValueError("At least one frame path is required")

    if not await check_ffmpeg_available():
        raise RuntimeError("ffmpeg is not installed or not found in PATH")

    n = len(frame_paths)
    durs = _compute_durations(n, durations, total_duration, crossfade)

    # Determine output path
    if output_path is None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="video_composer_"))
        output_path = tmp_dir / f"composed_{uuid4().hex[:8]}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Compute actual total duration for the silent audio track
    if n == 1:
        audio_duration = durs[0]
    else:
        audio_duration = sum(durs) - (n - 1) * crossfade

    # ---- Build FFmpeg command ----
    cmd: list[str] = ["ffmpeg", "-y"]

    # Input files: each as a loop with duration
    for i, frame in enumerate(frame_paths):
        cmd += ["-loop", "1", "-t", f"{durs[i]:.2f}", "-i", str(frame)]

    # Silent audio input (must be declared as input before filters/maps)
    cmd += ["-f", "lavfi", "-t", f"{audio_duration:.2f}",
            "-i", f"anullsrc=r=44100:cl=stereo"]

    # Build filter_complex
    filter_parts: list[str] = []

    # Step 1: scale + Ken Burns + format for each input
    for i in range(n):
        kb = _kb_filter(i, durs[i])
        # Scale to KB size, pad to fill, then zoompan produces OUT_WIDTH x OUT_HEIGHT
        base = (
            f"[{i}:v]scale={KB_WIDTH}:{KB_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={KB_WIDTH}:{KB_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,{kb},"
            f"format=yuv420p"
        )
        # Add drawtext overlay if provided
        if overlay_texts and i < len(overlay_texts) and overlay_texts[i]:
            base += "," + _drawtext_filter(overlay_texts[i], durs[i])

        base += f"[v{i}]"
        filter_parts.append(base)

    # Step 2: chain xfade transitions between frames
    if n == 1:
        # Single frame: just use it directly
        last_label = "v0"
    else:
        last_label = "v0"
        # Running offset: time at which next xfade starts
        offset = durs[0] - crossfade
        for i in range(1, n):
            out_label = f"xf{i}" if i < n - 1 else "vout"
            # Clamp offset to be non-negative
            safe_offset = max(0, offset)
            filter_parts.append(
                f"[{last_label}][v{i}]xfade=transition=fade:duration={crossfade:.2f}"
                f":offset={safe_offset:.2f}[{out_label}]"
            )
            last_label = out_label
            offset += durs[i] - crossfade

    final_label = last_label if n > 1 else "v0"

    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{final_label}]",
        "-map", f"{n}:a",
        "-c:v", "libx264",
        "-profile:v", "baseline",
        "-level", "3.1",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]

    logger.info("Running FFmpeg compose: %d frames, total ~%.1fs", n, total_duration)
    logger.debug("FFmpeg cmd: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace")[-2000:]
        logger.error("FFmpeg failed (rc=%d): %s", proc.returncode, err_msg)
        raise RuntimeError(f"FFmpeg failed with return code {proc.returncode}: {err_msg}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg produced no output file")

    logger.info("Video composed: %s (%.1f MB)", output_path, output_path.stat().st_size / 1e6)
    return output_path
