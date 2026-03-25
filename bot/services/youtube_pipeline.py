"""YouTube video pipeline — sectional assembly with B-roll, TTS, subtitles, music.

Extends the reels pipeline approach for long-form 16:9 YouTube content.
Reuses: video_composer (16:9 mode), tts_service, music_selector, video_montage.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from bot.services.drafts_store import get_draft, update_draft
from bot.services.music_selector import select_music
from bot.services.tts_service import generate_voiceover
from bot.services.video_composer import (
    FORMAT_LANDSCAPE,
    compose_video_from_frames,
)

logger = logging.getLogger(__name__)

# Where final YouTube videos are stored
YOUTUBE_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "youtube_video"
YOUTUBE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def _mix_audio(
    voiceover_path: Path | None,
    music_path: Path | None,
    output_path: Path,
    music_volume: float = 0.12,
) -> Path | None:
    """Mix voiceover and music. Lower music volume for long-form (0.12 vs 0.15 for reels)."""
    if voiceover_path and music_path:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            logger.warning("FFmpeg not available for audio mixing, using voiceover only")
            shutil.copy2(voiceover_path, output_path)
            return output_path

        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(voiceover_path),
            "-i", str(music_path),
            "-filter_complex",
            f"[1:a]volume={music_volume}[music];[0:a][music]amix=inputs=2:duration=first",
            "-ac", "2",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("Audio mixing failed: %s", stderr.decode(errors="replace")[:500])
            shutil.copy2(voiceover_path, output_path)
        return output_path

    if voiceover_path:
        shutil.copy2(voiceover_path, output_path)
        return output_path
    if music_path:
        shutil.copy2(music_path, output_path)
        return output_path
    return None


async def _merge_video_audio(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
) -> Path:
    """Merge a silent video with an audio track into the final MP4."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg is not installed or not found in PATH")

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",  # higher bitrate for YouTube
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace")[:1000]
        raise RuntimeError(f"FFmpeg merge failed (rc={proc.returncode}): {err}")
    return output_path


def _build_tts_segments_from_sections(sections: list[dict]) -> list[dict]:
    """Extract TTS text segments from YouTube script sections.

    Returns list of dicts with 'text', 'section_type', 'label' keys.
    Each section becomes one TTS segment.
    """
    segments: list[dict] = []
    for sec in sections:
        text = sec.get("speaker_text", "").strip() or sec.get("host_text", "").strip()
        if text:
            segments.append({
                "text": text,
                "duration_hint": None,
                "section_type": sec.get("section_type", ""),
                "label": sec.get("label", sec.get("section_type", "")),
            })
    return segments


def _collect_broll_image_paths(payload: dict, draft_id: str) -> list[Path]:
    """Collect B-roll image paths from payload."""
    from bot.services.reels_assets import ASSETS_DIR

    broll_map = payload.get("broll_map", [])
    paths: list[Path] = []
    asset_dir = ASSETS_DIR / draft_id

    for cue in broll_map:
        url = cue.get("image_url", "").strip()
        if url:
            filename = url.rsplit("/", 1)[-1] if "/" in url else url
            path = asset_dir / filename
            if path.exists():
                paths.append(path)
    return paths


async def compose_youtube_video(
    draft_id: str,
    *,
    progress_callback=None,
) -> dict:
    """Full YouTube pipeline: sections → TTS → B-roll → music → final MP4.

    Returns:
        {
            "video_path": str,
            "duration": float,
            "has_voiceover": bool,
            "has_music": bool,
            "sections_with_durations": list[dict],  # for metadata generation
            "steps_completed": list[str],
        }
    """
    steps_completed: list[str] = []

    # 1. Load draft
    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError(f"Draft not found: {draft_id}")

    payload = dict(draft.payload or {})
    sections = payload.get("sections", [])
    if not sections:
        raise ValueError(f"No sections found in draft {draft_id}")
    steps_completed.append("load_draft")

    # Prepare output directory
    video_dir = YOUTUBE_OUTPUT_DIR / draft_id
    video_dir.mkdir(parents=True, exist_ok=True)

    # 2. Generate TTS for each section
    if progress_callback:
        await progress_callback("tts", 10)

    tts_segments = _build_tts_segments_from_sections(sections)
    voiceover_path: Path | None = None
    segment_durations: list[float] = []

    if tts_segments:
        try:
            # Generate individual segment files for duration tracking
            from bot.services.tts_service import generate_single_audio
            import subprocess

            seg_paths: list[Path] = []
            for i, seg in enumerate(tts_segments):
                seg_path = video_dir / f"tts_seg_{i:03d}.mp3"
                await generate_single_audio(seg["text"], output_path=seg_path)
                seg_paths.append(seg_path)

                # Get real duration via ffprobe
                dur = _get_audio_duration(seg_path)
                segment_durations.append(dur)

            # Concatenate all segments
            voiceover_path = video_dir / "voiceover.mp3"
            await _concat_audio_files(seg_paths, voiceover_path)
            steps_completed.append("generate_voiceover")
        except Exception:
            logger.warning("Voiceover generation failed for draft %s", draft_id, exc_info=True)

    # 3. Compute real timecodes from TTS durations
    sections_with_durations: list[dict] = []
    running_time = 0.0
    for i, seg in enumerate(tts_segments):
        dur = segment_durations[i] if i < len(segment_durations) else 60.0
        sections_with_durations.append({
            "label": seg.get("label", f"Section {i}"),
            "section_type": seg.get("section_type", ""),
            "start_seconds": running_time,
            "duration_seconds": dur,
        })
        running_time += dur
    steps_completed.append("compute_timecodes")

    # 4. Compose B-roll clips (if images available)
    if progress_callback:
        await progress_callback("broll", 30)

    broll_paths = _collect_broll_image_paths(payload, draft_id)
    broll_video_path: Path | None = None

    if broll_paths:
        try:
            # Use video_composer in landscape mode to create B-roll clips
            broll_durations = []
            for cue in payload.get("broll_map", []):
                broll_durations.append(float(cue.get("duration", 4.0)))
            broll_durations = broll_durations[:len(broll_paths)]

            broll_video_path = video_dir / "broll_compiled.mp4"
            await compose_video_from_frames(
                frame_paths=broll_paths,
                durations=broll_durations,
                output_path=broll_video_path,
                total_duration=sum(broll_durations),
                crossfade=0.3,
                video_format=FORMAT_LANDSCAPE,
            )
            steps_completed.append("compose_broll")
        except Exception:
            logger.warning("B-roll composition failed for draft %s", draft_id, exc_info=True)
            broll_video_path = None

    # 5. Select background music
    if progress_callback:
        await progress_callback("music", 50)

    music_path: Path | None = None
    mood = str(payload.get("music_mood", payload.get("emotion", "calm")))
    if mood.strip():
        try:
            music_path = await select_music(mood)
            if music_path:
                steps_completed.append("select_music")
        except Exception:
            logger.warning("Music selection failed for draft %s", draft_id, exc_info=True)

    # 6. Mix audio (voiceover + music)
    if progress_callback:
        await progress_callback("mix_audio", 60)

    mixed_audio_path = video_dir / "mixed_audio.mp3"
    audio_result = await _mix_audio(voiceover_path, music_path, mixed_audio_path)
    if audio_result:
        steps_completed.append("mix_audio")

    # 7. Create silent video from B-roll (or placeholder)
    if progress_callback:
        await progress_callback("compose_video", 70)

    # For now, if we have B-roll clips, use them as the video track.
    # In future: interleave talking-head footage with B-roll at timecodes.
    silent_video_path = video_dir / "silent_video.mp4"
    if broll_video_path and broll_video_path.exists():
        shutil.copy2(broll_video_path, silent_video_path)
        steps_completed.append("use_broll_as_video")
    elif broll_paths:
        # Compose whatever B-roll images we have
        total_dur = running_time if running_time > 0 else 600.0
        await compose_video_from_frames(
            frame_paths=broll_paths,
            output_path=silent_video_path,
            total_duration=total_dur,
            video_format=FORMAT_LANDSCAPE,
        )
        steps_completed.append("compose_video_from_broll")
    else:
        # No video — create a black video matching audio duration
        total_dur = running_time if running_time > 0 else 600.0
        await _create_black_video(silent_video_path, total_dur)
        steps_completed.append("create_placeholder_video")

    # 8. Merge video + audio → final MP4
    if progress_callback:
        await progress_callback("merge", 85)

    final_path = video_dir / "final.mp4"
    if audio_result:
        await _merge_video_audio(silent_video_path, audio_result, final_path)
        steps_completed.append("merge_audio_video")
    else:
        shutil.copy2(silent_video_path, final_path)
        steps_completed.append("copy_silent_as_final")

    # 9. Tech check
    total_duration = _get_audio_duration(final_path)
    steps_completed.append("tech_check")

    # 10. Update draft payload
    if progress_callback:
        await progress_callback("finalize", 95)

    payload["video_path"] = str(final_path)
    payload["video_url"] = f"/generated/youtube_video/{draft_id}/final.mp4"
    payload["video_ready"] = True
    payload["sections_with_durations"] = sections_with_durations
    await update_draft(draft_id, payload=payload)
    steps_completed.append("update_draft")

    return {
        "video_path": str(final_path),
        "duration": total_duration,
        "has_voiceover": voiceover_path is not None,
        "has_music": music_path is not None,
        "sections_with_durations": sections_with_durations,
        "steps_completed": steps_completed,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_audio_duration(path: Path) -> float:
    """Get duration of an audio/video file via ffprobe."""
    import subprocess
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except (ValueError, AttributeError, subprocess.TimeoutExpired):
        return 0.0


async def _concat_audio_files(paths: list[Path], output: Path) -> None:
    """Concatenate multiple audio files using FFmpeg concat demuxer."""
    import tempfile

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        # Fallback: raw concatenation
        with open(output, "wb") as out_f:
            for p in paths:
                out_f.write(p.read_bytes())
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in paths:
            f.write(f"file '{p}'\n")
        concat_file = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_bin, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            str(output),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("Audio concat failed: %s", stderr.decode(errors="replace")[:300])
            # Fallback
            with open(output, "wb") as out_f:
                for p in paths:
                    out_f.write(p.read_bytes())
    finally:
        Path(concat_file).unlink(missing_ok=True)


async def _create_black_video(output: Path, duration: float) -> None:
    """Create a black 1920x1080 video with silent audio."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg not found")

    cmd = [
        ffmpeg_bin, "-y",
        "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:d={duration:.1f}:r=30",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", f"{duration:.1f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
