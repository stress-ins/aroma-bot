"""Generate SRT subtitles from reels script/transcript or video audio."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _wrap_subtitle(text: str, max_chars: int = 38) -> str:
    """Wrap text into max 2 lines of max_chars each."""
    if len(text) <= max_chars:
        return text
    words = text.split()
    line1: list[str] = []
    line2: list[str] = []
    length = 0
    for w in words:
        if length + len(w) + 1 <= max_chars:
            line1.append(w)
            length += len(w) + 1
        else:
            line2.append(w)
    l2 = " ".join(line2)
    if len(l2) > max_chars:
        l2 = l2[:max_chars - 1] + "…"
    return " ".join(line1) + "\n" + l2 if line2 else " ".join(line1)


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt_from_intervals(
    keep_intervals: list[list[float]],
    transcript_words: list[dict] | None = None,
    script_text: str = "",
) -> str:
    """Generate SRT subtitles aligned to keep intervals.

    If transcript_words provided (from Whisper): use word timestamps.
    Otherwise: split script_text evenly across intervals.

    transcript_words format: [{"word": "слово", "start": 0.5, "end": 1.2}, ...]
    """
    entries: list[str] = []

    if transcript_words:
        # Group words into ~5-word chunks
        chunk: list[dict] = []
        idx = 1
        for w in transcript_words:
            chunk.append(w)
            if len(chunk) >= 5 or w.get("word", "").rstrip().endswith((".", "!", "?", ",")):
                if chunk:
                    start = chunk[0]["start"]
                    end = chunk[-1]["end"]
                    text = " ".join(c["word"] for c in chunk).strip()
                    entries.append(
                        f"{idx}\n{_format_srt_time(start)} --> {_format_srt_time(end)}\n{text}\n"
                    )
                    idx += 1
                    chunk = []
        if chunk:
            start = chunk[0]["start"]
            end = chunk[-1]["end"]
            text = " ".join(c["word"] for c in chunk).strip()
            entries.append(
                f"{idx}\n{_format_srt_time(start)} --> {_format_srt_time(end)}\n{text}\n"
            )
    elif script_text and keep_intervals:
        # Split script into sentences and distribute across intervals
        sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())
        if not sentences:
            sentences = [script_text]

        total_duration = sum(e - s for s, e in keep_intervals)
        if total_duration <= 0:
            return ""

        # Map sentences to timeline
        current_time = 0.0
        idx = 1
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            # Proportional duration based on sentence length
            proportion = len(sentence) / max(sum(len(s) for s in sentences), 1)
            duration = max(1.0, total_duration * proportion)
            start = current_time
            end = min(current_time + duration, total_duration)

            entries.append(
                f"{idx}\n{_format_srt_time(start)} --> {_format_srt_time(end)}\n{sentence.strip()}\n"
            )
            idx += 1
            current_time = end

    return "\n".join(entries)


def save_srt(srt_content: str, output_path: str) -> str:
    """Save SRT content to file."""
    Path(output_path).write_text(srt_content, encoding="utf-8")
    return output_path


def build_subtitle_filter(
    srt_path: str,
    style: str = "bottom_bar",
    font_size: int = 28,
    color: str = "white",
    bg_opacity: float = 0.6,
) -> str:
    """Build FFmpeg subtitles filter string.

    Returns -vf fragment like: subtitles=file.srt:force_style='...'
    """
    # Escape path for FFmpeg
    safe_path = srt_path.replace("'", r"'\''").replace(":", r"\:")

    style_parts = [
        f"FontSize={font_size}",
        f"PrimaryColour=&H00FFFFFF" if color == "white" else f"PrimaryColour=&H00{color}",
        "Alignment=2",  # bottom center
        "MarginV=40",
        "FontName=Arial",
    ]

    if style == "bottom_bar":
        bg_hex = f"{int(bg_opacity * 255):02X}"
        style_parts.append(f"BackColour=&H{bg_hex}000000")
        style_parts.append("BorderStyle=4")
        style_parts.append("Shadow=0")
        style_parts.append("Outline=0")
    elif style == "centered":
        style_parts[2] = "Alignment=5"  # center
        style_parts.append("BorderStyle=1")
        style_parts.append("Outline=2")
        style_parts.append("Shadow=1")
    elif style == "karaoke":
        style_parts.append("BorderStyle=1")
        style_parts.append("Outline=2")
        style_parts.append(f"OutlineColour=&H80000000")
        style_parts.append("Shadow=0")
    elif style == "minimal":
        style_parts.append("BorderStyle=1")
        style_parts.append("Outline=1")
        style_parts.append("Shadow=1")

    force_style = ",".join(style_parts)
    return f"subtitles='{safe_path}':force_style='{force_style}'"


async def transcribe_video_to_srt(
    video_path: str,
    output_srt: str,
    *,
    model: str = "tiny",
    language: str = "ru",
) -> str:
    """Transcribe video audio with Whisper (subprocess) and generate SRT.

    Runs Whisper as a separate process to avoid OOM in the main server.
    Returns path to the generated SRT file, or "" on failure.
    """
    if not Path(video_path).exists():
        logger.warning("transcribe: video not found: %s", video_path)
        return ""

    # Extract audio to temp wav first (Whisper works better with wav)
    audio_path = str(Path(output_srt).with_suffix(".wav"))
    extract_cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *extract_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode != 0 or not Path(audio_path).exists():
        logger.error("transcribe: audio extraction failed (rc=%d)", proc.returncode)
        return ""

    # Run Whisper via subprocess (isolates memory)
    whisper_script = f"""
import whisper, json, sys
model = whisper.load_model("{model}")
result = model.transcribe("{audio_path}", language="{language}", word_timestamps=True)
segments = []
for seg in result.get("segments", []):
    segments.append({{"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}})
json.dump(segments, sys.stdout, ensure_ascii=False)
"""
    whisper_cmd = [sys.executable, "-c", whisper_script]
    logger.info("transcribe: running Whisper %s on %s", model, video_path)

    proc = await asyncio.create_subprocess_exec(
        *whisper_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    # Clean up audio
    try:
        Path(audio_path).unlink(missing_ok=True)
    except Exception:
        logger.warning("subtitles: suppressed exception", exc_info=True)
        pass

    if proc.returncode != 0:
        logger.error("transcribe: Whisper failed (rc=%d): %s", proc.returncode, stderr.decode("utf-8", errors="replace")[-300:])
        return ""

    try:
        segments = json.loads(stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.error("transcribe: could not parse Whisper output")
        return ""

    if not segments:
        logger.warning("transcribe: no segments found")
        return ""

    # Build SRT — split long segments into short readable chunks
    MAX_CHARS_PER_LINE = 38
    MAX_LINES = 2
    MAX_CHARS_PER_SUB = MAX_CHARS_PER_LINE * MAX_LINES

    srt_entries: list[dict] = []
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        seg_start = seg["start"]
        seg_end = seg["end"]
        seg_duration = seg_end - seg_start

        # Split long text into chunks
        if len(text) <= MAX_CHARS_PER_SUB:
            srt_entries.append({"start": seg_start, "end": seg_end, "text": _wrap_subtitle(text, MAX_CHARS_PER_LINE)})
        else:
            # Break into multiple entries proportional to length
            words = text.split()
            chunk_words: list[str] = []
            chunk_len = 0
            chunks: list[str] = []
            for w in words:
                if chunk_len + len(w) + 1 > MAX_CHARS_PER_SUB and chunk_words:
                    chunks.append(" ".join(chunk_words))
                    chunk_words = []
                    chunk_len = 0
                chunk_words.append(w)
                chunk_len += len(w) + 1
            if chunk_words:
                chunks.append(" ".join(chunk_words))

            total_chars = sum(len(c) for c in chunks)
            t = seg_start
            for c in chunks:
                proportion = len(c) / total_chars if total_chars else 1 / len(chunks)
                dur = seg_duration * proportion
                srt_entries.append({"start": t, "end": min(t + dur, seg_end), "text": _wrap_subtitle(c, MAX_CHARS_PER_LINE)})
                t += dur

    srt_lines: list[str] = []
    for i, entry in enumerate(srt_entries, 1):
        start = _format_srt_time(entry["start"])
        end = _format_srt_time(entry["end"])
        srt_lines.append(f"{i}\n{start} --> {end}\n{entry['text']}\n")

    srt_content = "\n".join(srt_lines)
    Path(output_srt).write_text(srt_content, encoding="utf-8")
    logger.info("transcribe: generated %d subtitle segments", len(srt_lines))
    return output_srt
