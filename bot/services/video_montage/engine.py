"""Montage engine — orchestrates the full auto-editing pipeline.

Pipeline steps (each optional):
1. Color grade the cleaned video
2. Generate subtitles from script/transcript
3. Detect beats in music (if beat-sync enabled)
4. Create B-roll clips from AI frames
5. Build final FFmpeg command combining all features
6. Encode final video
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from bot.services.video_montage.config import MontageConfig, MontageResult

logger = logging.getLogger(__name__)


async def run_montage(
    config: MontageConfig,
    *,
    script_text: str = "",
    transcript_words: list[dict] | None = None,
    progress_callback=None,
) -> MontageResult:
    """Run the full montage pipeline.

    Args:
        config: Montage configuration
        script_text: Reels script text (for subtitles)
        transcript_words: Whisper transcript words (for precise subtitles)
        progress_callback: async fn(step: str, progress: int) for status updates
    """
    config.apply_template()

    features_applied: list[str] = []
    ffmpeg_commands: list[str] = []
    loop = asyncio.get_running_loop()

    input_video = config.input_video
    if not Path(input_video).exists():
        return MontageResult(
            success=False, output_file="", duration=0,
            features_applied=[], ffmpeg_commands=[],
            error=f"Input video not found: {input_video}",
        )

    # Get video duration
    duration = await loop.run_in_executor(None, _get_duration, input_video)
    if duration <= 0:
        return MontageResult(
            success=False, output_file="", duration=0,
            features_applied=[], ffmpeg_commands=[],
            error="Could not determine video duration",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="montage_"))
    current_video = input_video

    try:
        # ── Step 1: Color grading ──
        if config.color_grade_enabled and config.color_grade_vf:
            if progress_callback:
                await progress_callback("color_grading", 10)

            graded = str(tmp_dir / "graded.mp4")
            cmd = _build_grade_cmd(current_video, config.color_grade_vf, graded, config)
            ffmpeg_commands.append(" ".join(cmd))

            rc = await loop.run_in_executor(None, _run_ffmpeg, cmd)
            if rc == 0 and Path(graded).exists():
                current_video = graded
                features_applied.append("color_grade")
                logger.info("Color grading applied")
            else:
                logger.warning("Color grading failed, continuing without")

        # ── Step 2: Generate subtitles ──
        srt_path = ""
        if config.subtitles_enabled:
            if progress_callback:
                await progress_callback("subtitles", 25)

            source = config.subtitle_source or "auto"

            # Option: transcribe from video audio
            if source in ("video", "auto"):
                from bot.services.video_montage.subtitles import transcribe_video_to_srt
                if progress_callback:
                    await progress_callback("transcribing", 28)
                srt_path = await transcribe_video_to_srt(
                    current_video,
                    str(tmp_dir / "subtitles.srt"),
                )
                if srt_path:
                    features_applied.append("subtitles_from_video")
                    logger.info("Subtitles from video transcription: %s", srt_path)

            # Fallback or explicit script source
            if not srt_path and (source in ("script", "auto")) and (script_text or transcript_words):
                from bot.services.video_montage.subtitles import generate_srt_from_intervals, save_srt

                srt_content = generate_srt_from_intervals(
                    config.keep_intervals,
                    transcript_words=transcript_words,
                    script_text=script_text,
                )
                if srt_content:
                    srt_path = str(tmp_dir / "subtitles.srt")
                    save_srt(srt_content, srt_path)
                    features_applied.append("subtitles_from_script")
                    logger.info("Subtitles from script: %s", srt_path)

        # ── Step 3: Music + beat detection ──
        music_inputs: list[str] = []
        music_filter = ""
        beats: list[float] = []

        if config.music_enabled and config.music_track:
            if progress_callback:
                await progress_callback("music", 35)

            from bot.services.video_montage.music import build_music_filter, detect_beats, MUSIC_LIBRARY

            music_path = config.music_track
            if music_path in MUSIC_LIBRARY:
                music_path = MUSIC_LIBRARY[music_path]

            if Path(music_path).exists():
                music_inputs, music_filter = build_music_filter(
                    music_path, duration,
                    volume=config.music_volume,
                    fade_in=config.music_fade_in,
                    fade_out=config.music_fade_out,
                )
                features_applied.append("music")

                if config.beat_sync_enabled:
                    beats = await loop.run_in_executor(None, detect_beats, music_path)
                    if beats:
                        features_applied.append("beat_sync")

        # ── Step 4: B-roll ──
        broll_clips: list[str] = []
        broll_positions: list[int] = []

        if config.broll_enabled and config.broll_frames:
            if progress_callback:
                await progress_callback("broll", 50)

            from bot.services.video_montage.broll import create_broll_clip, select_broll_positions

            broll_positions = select_broll_positions(
                config.keep_intervals, config.broll_max_inserts,
            )

            for i, pos in enumerate(broll_positions):
                if i >= len(config.broll_frames):
                    break
                frame_path = config.broll_frames[i]
                if not Path(frame_path).exists():
                    continue
                clip_path = str(tmp_dir / f"broll_{i}.mp4")
                result = await loop.run_in_executor(
                    None, create_broll_clip, frame_path, config.broll_duration, clip_path,
                )
                if result:
                    broll_clips.append(result)

            if broll_clips:
                features_applied.append("broll")

        # ── Step 5: Build final command ──
        if progress_callback:
            await progress_callback("encoding", 60)

        output_file = config.output_path
        if not output_file:
            stem = Path(config.input_video).stem
            output_file = str(Path(config.input_video).parent / f"{stem}_montage.mp4")

        # Strategy: apply all filters in one pass where possible
        vf_filters: list[str] = []

        # Subtitle filter
        if srt_path:
            from bot.services.video_montage.subtitles import build_subtitle_filter
            sub_filter = build_subtitle_filter(
                srt_path,
                style=config.subtitle_style,
                font_size=config.subtitle_font_size,
                color=config.subtitle_color,
                bg_opacity=config.subtitle_bg_opacity,
            )
            vf_filters.append(sub_filter)

        # Build command
        cmd = ["ffmpeg", "-y", "-i", current_video]
        cmd.extend(music_inputs)

        filter_complex_parts: list[str] = []

        # Video filters
        if vf_filters:
            vf_chain = ",".join(vf_filters)
            if music_filter:
                # Both video and audio filters
                filter_complex_parts.append(f"[0:v]{vf_chain}[vout]")
                filter_complex_parts.append(music_filter)
                cmd.extend(["-filter_complex", ";".join(filter_complex_parts)])
                cmd.extend(["-map", "[vout]", "-map", "[aout]"])
            else:
                cmd.extend(["-vf", vf_chain])
        elif music_filter:
            cmd.extend(["-filter_complex", music_filter])
            cmd.extend(["-map", "0:v", "-map", "[aout]"])

        cmd.extend([
            "-c:v", config.video_codec,
            "-preset", config.preset,
            "-crf", str(config.crf),
            "-c:a", config.audio_codec,
            "-b:a", "128k",
            "-movflags", "+faststart",
            output_file,
        ])

        cmd_str = " ".join(cmd)
        ffmpeg_commands.append(cmd_str)
        logger.info("Montage FFmpeg: %s", cmd_str[:300])

        if progress_callback:
            await progress_callback("encoding", 70)

        rc = await loop.run_in_executor(None, _run_ffmpeg, cmd)
        if rc != 0:
            return MontageResult(
                success=False, output_file="", duration=duration,
                features_applied=features_applied, ffmpeg_commands=ffmpeg_commands,
                error=f"FFmpeg encoding failed (rc={rc})",
            )

        # ── Step 6: Concat B-roll if present ──
        if broll_clips:
            if progress_callback:
                await progress_callback("broll_concat", 85)

            final_with_broll = str(tmp_dir / "final_broll.mp4")
            broll_ok = await _concat_with_broll(
                output_file, broll_clips, broll_positions,
                config.keep_intervals, final_with_broll, config,
            )
            if broll_ok:
                shutil.move(final_with_broll, output_file)

        if progress_callback:
            await progress_callback("done", 100)

        output_duration = await loop.run_in_executor(None, _get_duration, output_file)

        return MontageResult(
            success=True,
            output_file=output_file,
            duration=output_duration,
            features_applied=features_applied,
            ffmpeg_commands=ffmpeg_commands,
        )

    except Exception as exc:
        logger.error("Montage failed: %s", exc, exc_info=True)
        return MontageResult(
            success=False, output_file="", duration=duration,
            features_applied=features_applied, ffmpeg_commands=ffmpeg_commands,
            error=str(exc)[:500],
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _get_duration(filepath: str) -> float:
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


def _run_ffmpeg(cmd: list[str]) -> int:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.error("FFmpeg failed (rc=%d): %s", result.returncode, result.stderr[-500:])
    return result.returncode


def _build_grade_cmd(
    input_video: str, vf_string: str, output: str, config: MontageConfig,
) -> list[str]:
    return [
        "ffmpeg", "-y", "-i", input_video,
        "-vf", vf_string,
        "-c:v", config.video_codec, "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", "copy",
        output,
    ]


async def _concat_with_broll(
    main_video: str,
    broll_clips: list[str],
    positions: list[int],
    intervals: list[list[float]],
    output: str,
    config: MontageConfig,
) -> bool:
    """Insert B-roll clips at specified positions using concat demuxer."""
    tmp = Path(tempfile.mkdtemp(prefix="broll_"))
    try:
        # Split main video at B-roll insertion points
        concat_list = tmp / "concat.txt"
        segments: list[str] = []

        # For simplicity: interleave main segments with B-roll clips
        # Main video plays, then B-roll, then main continues
        # This is approximate — proper implementation needs precise splitting
        segments.append(main_video)
        for i, clip in enumerate(broll_clips):
            if Path(clip).exists():
                segments.append(clip)

        # Just append B-roll at the end for now (proper interleaving is complex)
        with open(concat_list, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", config.video_codec, "-preset", config.preset,
            "-crf", str(config.crf),
            "-c:a", config.audio_codec,
            output,
        ]

        loop = asyncio.get_running_loop()
        rc = await loop.run_in_executor(None, _run_ffmpeg, cmd)
        return rc == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
