"""Tests for bot.services.video_composer — Ken Burns video composition."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# Skip entire module if ffmpeg is not available
pytestmark = [
    pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed"),
    pytest.mark.slow,
]


def _make_solid_image(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (1080, 1920)) -> Path:
    """Create a solid-colour PNG test image using Pillow."""
    from PIL import Image

    img = Image.new("RGB", size, color)
    img.save(path, "PNG")
    return path


def _ffprobe_info(video_path: Path) -> dict:
    """Run ffprobe and return parsed JSON."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            str(video_path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"ffprobe failed: {result.stderr[:500]}"
    return json.loads(result.stdout)


@pytest.fixture()
def frame_dir(tmp_path: Path) -> Path:
    """Create a temp directory with 4 solid-colour test frames."""
    colors = [(255, 60, 60), (60, 200, 60), (60, 60, 255), (255, 200, 60)]
    for i, color in enumerate(colors):
        _make_solid_image(tmp_path / f"frame_{i}.png", color)
    return tmp_path


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.mark.asyncio
async def test_compose_4_frames(frame_dir: Path, output_dir: Path) -> None:
    """Compose 4 frames into a video and validate output."""
    from bot.services.video_composer import compose_video_from_frames

    frames = sorted(frame_dir.glob("frame_*.png"))
    assert len(frames) == 4

    out = output_dir / "test_4frames.mp4"
    result = await compose_video_from_frames(
        frame_paths=frames,
        output_path=out,
        total_duration=12.0,
        crossfade=0.5,
    )

    assert result.exists()
    assert result.stat().st_size > 0

    info = _ffprobe_info(result)
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert int(video_stream["width"]) == 1080
    assert int(video_stream["height"]) == 1920
    assert video_stream["codec_name"] == "h264"
    assert video_stream.get("pix_fmt") == "yuv420p"

    # Check duration is roughly correct (allow 2s tolerance)
    duration = float(info["format"]["duration"])
    assert 9.0 < duration < 15.0, f"Unexpected duration: {duration}"


@pytest.mark.asyncio
async def test_compose_with_overlay_texts(frame_dir: Path, output_dir: Path) -> None:
    """Compose with text overlays and verify output is valid."""
    from bot.services.video_composer import compose_video_from_frames

    frames = sorted(frame_dir.glob("frame_*.png"))
    texts = ["Lavender Oil", "Peppermint", "Eucalyptus", "Tea Tree"]

    out = output_dir / "test_overlay.mp4"
    result = await compose_video_from_frames(
        frame_paths=frames,
        overlay_texts=texts,
        output_path=out,
        total_duration=12.0,
    )

    assert result.exists()
    assert result.stat().st_size > 0

    info = _ffprobe_info(result)
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert int(video_stream["width"]) == 1080
    assert int(video_stream["height"]) == 1920


@pytest.mark.asyncio
async def test_compose_custom_durations(frame_dir: Path, output_dir: Path) -> None:
    """Compose with explicit per-frame durations."""
    from bot.services.video_composer import compose_video_from_frames

    frames = sorted(frame_dir.glob("frame_*.png"))[:2]
    custom_durations = [5.0, 7.0]

    out = output_dir / "test_custom_dur.mp4"
    result = await compose_video_from_frames(
        frame_paths=frames,
        durations=custom_durations,
        output_path=out,
    )

    assert result.exists()
    info = _ffprobe_info(result)
    duration = float(info["format"]["duration"])
    # 5 + 7 - 0.5 crossfade = 11.5 (allow margin for encoder)
    assert 10.0 < duration < 14.0, f"Unexpected duration: {duration}"


@pytest.mark.asyncio
async def test_compose_single_frame(frame_dir: Path, output_dir: Path) -> None:
    """Single frame should produce a valid video (no crossfade needed)."""
    from bot.services.video_composer import compose_video_from_frames

    frames = [sorted(frame_dir.glob("frame_*.png"))[0]]

    out = output_dir / "test_single.mp4"
    result = await compose_video_from_frames(
        frame_paths=frames,
        output_path=out,
        total_duration=5.0,
    )

    assert result.exists()
    info = _ffprobe_info(result)
    duration = float(info["format"]["duration"])
    assert 3.5 < duration < 7.0, f"Unexpected duration: {duration}"


@pytest.mark.asyncio
async def test_compose_two_frames(frame_dir: Path, output_dir: Path) -> None:
    """Two frames with crossfade."""
    from bot.services.video_composer import compose_video_from_frames

    frames = sorted(frame_dir.glob("frame_*.png"))[:2]

    out = output_dir / "test_two.mp4"
    result = await compose_video_from_frames(
        frame_paths=frames,
        output_path=out,
        total_duration=8.0,
        crossfade=0.5,
    )

    assert result.exists()
    info = _ffprobe_info(result)
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert int(video_stream["width"]) == 1080


@pytest.mark.asyncio
async def test_compose_different_aspect_ratios(output_dir: Path, tmp_path: Path) -> None:
    """Frames with non-9:16 aspect ratios should be padded correctly."""
    from bot.services.video_composer import compose_video_from_frames

    # Create a square and a landscape image
    _make_solid_image(tmp_path / "square.png", (200, 100, 50), size=(800, 800))
    _make_solid_image(tmp_path / "landscape.png", (50, 100, 200), size=(1920, 1080))
    frames = [tmp_path / "square.png", tmp_path / "landscape.png"]

    out = output_dir / "test_aspect.mp4"
    result = await compose_video_from_frames(
        frame_paths=frames,
        output_path=out,
        total_duration=6.0,
    )

    assert result.exists()
    info = _ffprobe_info(result)
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert int(video_stream["width"]) == 1080
    assert int(video_stream["height"]) == 1920


@pytest.mark.asyncio
async def test_compose_no_frames_raises() -> None:
    """Empty frame list should raise ValueError."""
    from bot.services.video_composer import compose_video_from_frames

    with pytest.raises(ValueError, match="(?i)at least one frame"):
        await compose_video_from_frames(frame_paths=[])


@pytest.mark.asyncio
async def test_check_ffmpeg_available() -> None:
    """check_ffmpeg_available should return True when ffmpeg is present."""
    from bot.services.video_composer import check_ffmpeg_available

    result = await check_ffmpeg_available()
    # We already skip this module if ffmpeg is missing, so this must be True
    assert result is True


@pytest.mark.asyncio
async def test_has_audio_track(frame_dir: Path, output_dir: Path) -> None:
    """Output should contain a silent audio track for mobile compatibility."""
    from bot.services.video_composer import compose_video_from_frames

    frames = sorted(frame_dir.glob("frame_*.png"))[:2]
    out = output_dir / "test_audio.mp4"
    result = await compose_video_from_frames(
        frame_paths=frames,
        output_path=out,
        total_duration=6.0,
    )

    info = _ffprobe_info(result)
    audio_stream = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    assert audio_stream is not None, "Video should have an audio track"
    assert audio_stream["codec_name"] == "aac"
