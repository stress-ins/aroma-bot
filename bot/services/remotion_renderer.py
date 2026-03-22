"""Remotion video renderer — Python bridge to npx remotion render CLI.

Provides the same interface as ``video_composer.compose_video_from_frames()``
but renders via Remotion (React-based video framework) instead of FFmpeg.

Remotion replaces ONLY the composition step (frames → silent MP4).
Audio mixing and merging remain handled by FFmpeg in video_pipeline.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

# Limit concurrent Remotion renders (Chromium is memory-heavy)
_render_semaphore = asyncio.Semaphore(1)

# Remotion project directory
REMOTION_DIR = Path(__file__).parent.parent.parent / "remotion"

# Composition name → template mapping
TEMPLATE_MAP = {
    "aroma": "AromaReel",
    "educational": "EducationalReel",
    "promo": "PromoReel",
}

DEFAULT_FRAME_DURATION = 7.5
DEFAULT_CROSSFADE = 0.5
DEFAULT_TOTAL_DURATION = 30.0
FPS = 30


def _check_remotion_available() -> bool:
    """Check if the Remotion project is set up (node_modules present)."""
    return (REMOTION_DIR / "node_modules").exists()


def _compute_durations(
    n_frames: int,
    total_duration: float,
    crossfade: float,
) -> list[float]:
    """Distribute total_duration evenly across frames, accounting for crossfade."""
    if n_frames == 1:
        return [total_duration]
    total_with_overlap = total_duration + (n_frames - 1) * crossfade
    per_frame = max(total_with_overlap / n_frames, 2.0)
    return [per_frame] * n_frames


async def compose_video_remotion(
    frame_paths: list[Path],
    overlay_texts: list[str] | None = None,
    output_path: Path | None = None,
    total_duration: float = DEFAULT_TOTAL_DURATION,
    crossfade: float = DEFAULT_CROSSFADE,
    template: str = "aroma",
    text_animation: str = "fade",
) -> Path:
    """Compose a silent video from still images using Remotion.

    Args:
        frame_paths: List of image file paths.
        overlay_texts: Optional text overlays per frame.
        output_path: Where to write the output MP4.
        total_duration: Target total video duration in seconds.
        crossfade: Crossfade duration between frames in seconds.
        template: Composition template (aroma, educational, promo).
        text_animation: Text animation style (fade, slide-up, typewriter, scale-in).

    Returns:
        Path to the rendered MP4 file.

    Raises:
        RuntimeError: If Remotion is not installed or rendering fails.
    """
    if not frame_paths:
        raise ValueError("At least one frame path is required")

    if not _check_remotion_available():
        raise RuntimeError(
            "Remotion is not installed. Run 'cd remotion && npm ci' first."
        )

    npx_bin = shutil.which("npx")
    if not npx_bin:
        raise RuntimeError("npx is not found in PATH. Install Node.js first.")

    n = len(frame_paths)
    durations = _compute_durations(n, total_duration, crossfade)
    composition_id = TEMPLATE_MAP.get(template, "AromaReel")

    # Build props JSON
    frames_props = []
    for i, path in enumerate(frame_paths):
        overlay = ""
        if overlay_texts and i < len(overlay_texts):
            overlay = overlay_texts[i] or ""
        frames_props.append({
            "imagePath": str(path.resolve()),
            "duration": durations[i],
            "overlayText": overlay,
            "motionType": i % 4,
        })

    props: dict = {
        "frames": frames_props,
        "crossfadeDuration": crossfade,
        "textAnimation": text_animation,
        "fps": FPS,
    }

    # Add template-specific defaults
    if template == "educational":
        props["showStepNumbers"] = True
        props["showProgressBar"] = True
    elif template == "promo":
        props["brandColor"] = "#C4704B"
        props["ctaText"] = "Узнать больше"

    # Write props to temp file
    props_file = Path(tempfile.mktemp(suffix=".json", prefix="remotion_props_"))
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    # Determine output path
    if output_path is None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="remotion_output_"))
        output_path = tmp_dir / f"remotion_{uuid4().hex[:8]}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build Remotion CLI command
    cmd = [
        npx_bin, "remotion", "render",
        str(REMOTION_DIR / "src" / "index.ts"),
        composition_id,
        str(output_path),
        f"--props={props_file}",
        "--codec=h264",
        "--crf=18",
        "--log=error",
    ]

    logger.info(
        "Rendering via Remotion: %d frames, template=%s, ~%.1fs",
        n, template, total_duration,
    )
    logger.debug("Remotion cmd: %s", " ".join(cmd))

    async with _render_semaphore:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REMOTION_DIR),
        )
        stdout, stderr = await proc.communicate()

    # Cleanup props file
    try:
        props_file.unlink(missing_ok=True)
    except OSError:
        pass

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace")[-2000:]
        logger.error("Remotion render failed (rc=%d): %s", proc.returncode, err_msg)
        raise RuntimeError(
            f"Remotion render failed with return code {proc.returncode}: {err_msg}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Remotion produced no output file")

    logger.info(
        "Remotion render complete: %s (%.1f MB)",
        output_path, output_path.stat().st_size / 1e6,
    )
    return output_path


async def render_still(
    frame_paths: list[Path],
    overlay_texts: list[str] | None = None,
    output_dir: Path | None = None,
    total_duration: float = DEFAULT_TOTAL_DURATION,
    crossfade: float = DEFAULT_CROSSFADE,
    template: str = "aroma",
    text_animation: str = "fade",
    frame_indices: list[int] | None = None,
    count: int = 4,
) -> list[Path]:
    """Render key frame stills using ``npx remotion still``.

    Returns list of PNG paths for preview filmstrip.
    """
    if not _check_remotion_available():
        raise RuntimeError("Remotion is not installed.")

    npx_bin = shutil.which("npx")
    if not npx_bin:
        raise RuntimeError("npx is not found in PATH.")

    n = len(frame_paths)
    durations = _compute_durations(n, total_duration, crossfade)
    composition_id = TEMPLATE_MAP.get(template, "AromaReel")

    # Build same props as for render
    frames_props = []
    for i, path in enumerate(frame_paths):
        overlay = ""
        if overlay_texts and i < len(overlay_texts):
            overlay = overlay_texts[i] or ""
        frames_props.append({
            "imagePath": str(path.resolve()),
            "duration": durations[i],
            "overlayText": overlay,
            "motionType": i % 4,
        })

    props: dict = {
        "frames": frames_props,
        "crossfadeDuration": crossfade,
        "textAnimation": text_animation,
        "fps": FPS,
    }

    if template == "educational":
        props["showStepNumbers"] = True
        props["showProgressBar"] = True
    elif template == "promo":
        props["brandColor"] = "#C4704B"
        props["ctaText"] = "Узнать больше"

    # Calculate total frames
    total_seconds = sum(durations)
    crossfade_overlap = max(0, n - 1) * crossfade
    total_frames = int((total_seconds - crossfade_overlap) * FPS)

    # Determine which frames to render
    if frame_indices is None:
        # Evenly spaced key frames
        step = max(1, total_frames // (count + 1))
        frame_indices = [step * (i + 1) for i in range(count)]
        frame_indices = [f for f in frame_indices if f < total_frames]

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="remotion_stills_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    props_file = Path(tempfile.mktemp(suffix=".json", prefix="remotion_props_"))
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    results: list[Path] = []

    async with _render_semaphore:
        for idx, frame_num in enumerate(frame_indices):
            out_path = output_dir / f"preview_{idx}.png"
            cmd = [
                npx_bin, "remotion", "still",
                str(REMOTION_DIR / "src" / "index.ts"),
                composition_id,
                str(out_path),
                f"--props={props_file}",
                f"--frame={frame_num}",
                "--log=error",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(REMOTION_DIR),
            )
            await proc.communicate()
            if proc.returncode == 0 and out_path.exists():
                results.append(out_path)

    try:
        props_file.unlink(missing_ok=True)
    except OSError:
        pass

    return results
