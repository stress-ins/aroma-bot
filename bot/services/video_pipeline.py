"""Video pipeline orchestrator — frames + voiceover + music -> final MP4.

Ties together ``video_composer``, ``tts_service``, and ``music_selector``
to produce a complete reel from a draft.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from bot.services.drafts_store import get_draft, update_draft
from bot.services.music_selector import select_music
from bot.services.reels_assets import ASSETS_DIR
from bot.services.tts_service import extract_voiceover_segments, generate_voiceover
from bot.services.video_composer import compose_video_from_frames

logger = logging.getLogger(__name__)

# Where final videos are stored
VIDEO_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "reels_video"
VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def _mix_audio(
    voiceover_path: Path | None,
    music_path: Path | None,
    output_path: Path,
) -> Path | None:
    """Mix voiceover and music into a single audio file.

    - If both are provided: mix with music at reduced volume.
    - If only one: return that file directly (copy to output_path).
    - If neither: return None (silent video).
    """
    if voiceover_path and music_path:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            # Fallback to voiceover only
            logger.warning("FFmpeg not available for audio mixing, using voiceover only")
            shutil.copy2(voiceover_path, output_path)
            return output_path

        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(voiceover_path),
            "-i", str(music_path),
            "-filter_complex",
            "[1:a]volume=0.15[music];[0:a][music]amix=inputs=2:duration=first",
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
            # Fallback to voiceover
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
        "-b:a", "128k",
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


def _find_frame_images(draft_id: str, payload: dict) -> list[Path]:
    """Locate frame image files for a draft.

    Looks for images in ``data/reels_assets/{draft_id}/`` using URLs
    stored in the draft payload (v2 frames or v1 storyboard).
    """
    asset_dir = ASSETS_DIR / draft_id
    if not asset_dir.exists():
        return []

    # Try v2 frames first
    frames = payload.get("frames", [])
    if frames and isinstance(frames, list):
        paths = []
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            url = str(frame.get("image_url", "")).strip()
            if url:
                # URL format: /generated/reels_assets/{draft_id}/{filename}
                filename = url.rsplit("/", 1)[-1] if "/" in url else url
                path = asset_dir / filename
                if path.exists():
                    paths.append(path)
        return paths

    # Try v1 storyboard
    storyboard = payload.get("storyboard", [])
    if storyboard and isinstance(storyboard, list):
        paths = []
        for item in storyboard:
            if not isinstance(item, dict):
                continue
            asset = item.get("current_asset", {})
            if isinstance(asset, dict):
                url = str(asset.get("url", "")).strip()
                if url:
                    filename = url.rsplit("/", 1)[-1] if "/" in url else url
                    path = asset_dir / filename
                    if path.exists():
                        paths.append(path)
        return paths

    # Fallback: glob for PNG/JPG images in the asset directory
    found = sorted(asset_dir.glob("frame_*.png")) + sorted(asset_dir.glob("frame_*.jpg"))
    return found


def _extract_overlay_texts(payload: dict) -> list[str]:
    """Extract overlay texts from draft payload frames."""
    texts: list[str] = []

    # v2 frames
    frames = payload.get("frames", [])
    if frames and isinstance(frames, list):
        for frame in frames:
            if isinstance(frame, dict):
                texts.append(str(frame.get("overlay_text", "")).strip())
            else:
                texts.append("")
        return texts

    # v1 storyboard
    storyboard = payload.get("storyboard", [])
    if storyboard and isinstance(storyboard, list):
        for item in storyboard:
            if isinstance(item, dict):
                texts.append(str(item.get("overlay_text", "")).strip())
            else:
                texts.append("")
        return texts

    return texts


async def compose_reel(draft_id: str) -> dict:
    """Full pipeline: frames -> video -> voiceover -> music -> final MP4.

    Returns::

        {
            "video_path": str,
            "duration": float,
            "has_voiceover": bool,
            "has_music": bool,
            "steps_completed": [str],
        }
    """
    steps_completed: list[str] = []

    # 1. Load draft
    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError(f"Draft not found: {draft_id}")

    payload = dict(draft.payload or {})
    steps_completed.append("load_draft")

    # 2. Find frame images
    frame_paths = _find_frame_images(draft_id, payload)
    if not frame_paths:
        raise ValueError(f"No frame images found for draft {draft_id}")
    steps_completed.append("find_frames")

    # 3. Extract overlay texts
    overlay_texts = _extract_overlay_texts(payload)
    steps_completed.append("extract_overlays")

    # 4. Extract voiceover segments from scenario
    scenario = str(payload.get("scenario", ""))
    voiceover_segments = extract_voiceover_segments(scenario) if scenario.strip() else []
    steps_completed.append("extract_voiceover_text")

    # Prepare output directory
    draft_video_dir = VIDEO_OUTPUT_DIR / draft_id
    draft_video_dir.mkdir(parents=True, exist_ok=True)

    # 5. Compose silent video from frames
    silent_video_path = draft_video_dir / "silent_video.mp4"
    await compose_video_from_frames(
        frame_paths=frame_paths,
        overlay_texts=overlay_texts if any(overlay_texts) else None,
        output_path=silent_video_path,
    )
    steps_completed.append("compose_video")

    # 6. Generate voiceover (if text found)
    voiceover_path: Path | None = None
    if voiceover_segments:
        try:
            voiceover_path = await generate_voiceover(
                voiceover_segments,
                output_path=draft_video_dir / "voiceover.mp3",
            )
            steps_completed.append("generate_voiceover")
        except Exception:
            logger.warning("Voiceover generation failed for draft %s", draft_id, exc_info=True)

    # 7. Select background music
    music_path: Path | None = None
    mood = str(payload.get("mood", payload.get("emotion", "calm")))
    if mood.strip():
        try:
            music_path = await select_music(mood)
            if music_path:
                steps_completed.append("select_music")
        except Exception:
            logger.warning("Music selection failed for draft %s", draft_id, exc_info=True)

    # 8. Mix audio
    mixed_audio_path = draft_video_dir / "mixed_audio.mp3"
    audio_result = await _mix_audio(voiceover_path, music_path, mixed_audio_path)
    if audio_result:
        steps_completed.append("mix_audio")

    # 9. Merge video + audio -> final MP4
    final_path = draft_video_dir / "final.mp4"
    if audio_result:
        await _merge_video_audio(silent_video_path, audio_result, final_path)
        steps_completed.append("merge_audio_video")
    else:
        # No audio — the silent video is the final product
        shutil.copy2(silent_video_path, final_path)
        steps_completed.append("copy_silent_as_final")

    # 10. Tech check (optional)
    tech_check_result = None
    try:
        from bot.services.reels_video import _tech_check_ffprobe, _ffprobe_available

        if _ffprobe_available():
            tech_check_result = _tech_check_ffprobe(final_path)
            steps_completed.append("tech_check")
    except Exception:
        logger.debug("Tech check skipped for draft %s", draft_id, exc_info=True)

    # 11. Update draft payload
    payload["video_path"] = str(final_path)
    payload["video_url"] = f"/generated/reels_video/{draft_id}/final.mp4"
    payload["video_ready"] = True
    if tech_check_result:
        payload["tech_check"] = tech_check_result
    await update_draft(draft_id, payload=payload)
    steps_completed.append("update_draft")

    # Compute duration from tech check or estimate
    duration = 0.0
    if tech_check_result and isinstance(tech_check_result.get("info"), dict):
        duration = float(tech_check_result["info"].get("duration_s", 0))
    if not duration and final_path.exists():
        # Rough estimate: frame count * default duration
        duration = len(frame_paths) * 7.5

    return {
        "video_path": str(final_path),
        "duration": duration,
        "has_voiceover": voiceover_path is not None,
        "has_music": music_path is not None,
        "steps_completed": steps_completed,
    }
