"""FFmpeg command construction for single-file and split modes."""

from __future__ import annotations

import logging
from pathlib import Path

from bot.services.video_processor.config import ProcessorConfig
from bot.services.video_processor.filter_engine import Interval

logger = logging.getLogger(__name__)

# Supported xfade transition types
XFADE_TRANSITIONS = frozenset({
    "fade", "wipeleft", "wiperight", "slideleft", "slideright",
    "circlecrop", "dissolve", "pixelize", "radial", "zoomin",
})


_CONCAT_DEMUXER_THRESHOLD = 20  # Use concat demuxer for >20 segments (saves memory)


def build_single(
    input_file: Path,
    intervals: list[Interval],
    output_file: Path,
    config: ProcessorConfig,
) -> list[str]:
    """Build FFmpeg command for concatenating intervals into one output file.

    If ``config.transitions_enabled`` is True, uses xfade/acrossfade between
    segments. Otherwise uses the simpler concat filter.

    For many segments (>20), uses 2-pass concat demuxer to avoid OOM:
    1. Extract each segment with -c copy (fast, no re-encode)
    2. Concat all segments via concat demuxer + re-encode once
    """
    if not intervals:
        raise ValueError("No intervals to process")

    if config.transitions_enabled and len(intervals) > 1:
        return _build_with_xfade(input_file, intervals, output_file, config)

    if len(intervals) > _CONCAT_DEMUXER_THRESHOLD:
        return _build_with_demuxer(input_file, intervals, output_file, config)

    return _build_with_concat(input_file, intervals, output_file, config)


def _build_with_concat(
    input_file: Path,
    intervals: list[Interval],
    output_file: Path,
    config: ProcessorConfig,
) -> list[str]:
    """Build FFmpeg command using trim + concat (no transitions)."""
    n = len(intervals)
    filter_parts: list[str] = []

    # Trim each interval
    for i, iv in enumerate(intervals):
        filter_parts.append(
            f"[0:v]trim=start={iv.start:.3f}:end={iv.end:.3f},"
            f"setpts=PTS-STARTPTS[v{i}]",
        )
        filter_parts.append(
            f"[0:a]atrim=start={iv.start:.3f}:end={iv.end:.3f},"
            f"asetpts=PTS-STARTPTS[a{i}]",
        )

    # Concat all segments
    v_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_parts.append(f"{v_inputs}concat=n={n}:v=1:a=1[outv][outa]")

    filter_complex = ";".join(filter_parts)

    return [
        "ffmpeg", "-y",
        "-i", str(input_file),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", config.video_codec,
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", config.audio_codec,
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_file),
    ]


def _build_with_demuxer(
    input_file: Path,
    intervals: list[Interval],
    output_file: Path,
    config: ProcessorConfig,
) -> list[str]:
    """Build 2-pass concat for many segments — avoids OOM.

    Pass 1: Extract each segment as separate file (stream copy, fast)
    Pass 2: Concat all segment files via concat demuxer

    Returns the command for pass 2. Pass 1 commands are stored in
    _demuxer_pre_commands attribute of the returned list.
    """
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix="vp_concat_"))
    concat_list = tmp_dir / "concat.txt"

    pre_commands: list[list[str]] = []
    segment_files: list[Path] = []

    for i, iv in enumerate(intervals):
        seg_path = tmp_dir / f"seg_{i:04d}.mp4"
        segment_files.append(seg_path)
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{iv.start:.3f}",
            "-i", str(input_file),
            "-t", f"{iv.duration:.3f}",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(seg_path),
        ]
        pre_commands.append(cmd)

    # Write concat list
    with open(concat_list, "w") as f:
        for seg in segment_files:
            f.write(f"file '{seg}'\n")

    # Pass 2: concat + re-encode
    final_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", config.video_codec,
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", config.audio_codec,
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_file),
    ]

    # Store pre-commands on the list object for processor to pick up
    final_cmd = _DemuxerCommand(final_cmd)
    final_cmd.pre_commands = pre_commands
    final_cmd.tmp_dir = str(tmp_dir)
    return final_cmd


class _DemuxerCommand(list):
    """List subclass carrying extra attrs for 2-pass concat."""
    pre_commands: list[list[str]] = []
    tmp_dir: str = ""


def _build_with_xfade(
    input_file: Path,
    intervals: list[Interval],
    output_file: Path,
    config: ProcessorConfig,
) -> list[str]:
    """Build FFmpeg command using trim + xfade/acrossfade transitions."""
    n = len(intervals)
    xf_dur = config.transition_duration
    transition = config.transition_type
    if transition not in XFADE_TRANSITIONS:
        logger.warning("Unknown transition '%s', falling back to 'fade'", transition)
        transition = "fade"

    filter_parts: list[str] = []

    # Step 1: trim each interval
    for i, iv in enumerate(intervals):
        filter_parts.append(
            f"[0:v]trim=start={iv.start:.3f}:end={iv.end:.3f},"
            f"setpts=PTS-STARTPTS[v{i}]",
        )
        filter_parts.append(
            f"[0:a]atrim=start={iv.start:.3f}:end={iv.end:.3f},"
            f"asetpts=PTS-STARTPTS[a{i}]",
        )

    # Step 2: chain xfade for video
    last_v = "v0"
    offset = intervals[0].duration - xf_dur
    for i in range(1, n):
        out_label = f"xv{i}" if i < n - 1 else "outv"
        safe_offset = max(0.0, offset)
        # Reduce xfade duration if segment is too short
        effective_xf = min(xf_dur, intervals[i].duration * 0.5)
        filter_parts.append(
            f"[{last_v}][v{i}]xfade=transition={transition}"
            f":duration={effective_xf:.3f}:offset={safe_offset:.3f}[{out_label}]",
        )
        last_v = out_label
        offset += intervals[i].duration - effective_xf

    # Step 3: chain acrossfade for audio
    last_a = "a0"
    for i in range(1, n):
        out_label = f"xa{i}" if i < n - 1 else "outa"
        effective_xf = min(xf_dur, intervals[i].duration * 0.5)
        filter_parts.append(
            f"[{last_a}][a{i}]acrossfade=d={effective_xf:.3f}:c1=tri:c2=tri[{out_label}]",
        )
        last_a = out_label

    filter_complex = ";".join(filter_parts)

    return [
        "ffmpeg", "-y",
        "-i", str(input_file),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", config.video_codec,
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", config.audio_codec,
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_file),
    ]


def build_split(
    input_file: Path,
    intervals: list[Interval],
    output_dir: Path,
    config: ProcessorConfig,
) -> list[tuple[list[str], Path]]:
    """Build FFmpeg commands for split mode — one per clip.

    Returns list of (command, output_path) tuples.
    """
    commands: list[tuple[list[str], Path]] = []

    for i, iv in enumerate(intervals):
        if iv.duration < config.split_min_clip_duration:
            logger.debug(
                "Skipping interval %.3f-%.3f (%.2fs < min %.2fs)",
                iv.start, iv.end, iv.duration, config.split_min_clip_duration,
            )
            continue

        filename = config.split_naming_pattern.format(i + 1)
        out_path = output_dir / filename
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
        commands.append((cmd, out_path))

    return commands
