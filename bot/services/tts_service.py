"""Text-to-speech voiceover service using edge-tts (Microsoft Edge TTS).

Provides Russian-language TTS for reels/video voiceovers.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

# Default output directory
TTS_OUTPUT_DIR = Path(__file__).parent.parent.parent / "generated" / "tts"
TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Voices suitable for wellness / aromatherapy content
DEFAULT_VOICE = "ru-RU-DmitryNeural"  # male, calm
ALTERNATIVE_VOICE = "ru-RU-SvetlanaNeural"  # female

# Patterns to extract voiceover text from reels scenarios
_VOICEOVER_PATTERNS = [
    re.compile(
        r'(?:Закадровый голос|Голос за кадром|Voiceover|VO)\s*[:：]\s*[«"\u201c]?(.+?)[»"\u201d]?\s*$',
        re.MULTILINE | re.IGNORECASE,
    ),
]

# Pattern for standalone "Текст: ..." lines (used in frame-based scenarios)
_FRAME_TEXT_PATTERN = re.compile(
    r'^\s*(?:Текст|Text|Голос|Voice)\s*[:：]\s*[«"\u201c]?(.+?)[»"\u201d]?\s*$',
    re.MULTILINE | re.IGNORECASE,
)


async def generate_single_audio(
    text: str,
    voice: str = DEFAULT_VOICE,
    output_path: Path | None = None,
) -> Path:
    """Generate audio for a single text string.

    Args:
        text: Text to convert to speech.
        voice: Edge-tts voice name.
        output_path: Where to save the file. Auto-generated if None.

    Returns:
        Path to the generated MP3 file.
    """
    import edge_tts

    if output_path is None:
        output_path = TTS_OUTPUT_DIR / f"tts_{uuid4().hex[:12]}.mp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))

    logger.info("TTS generated: %s (%d bytes)", output_path.name, output_path.stat().st_size)
    return output_path


async def generate_voiceover(
    text_segments: list[dict],
    voice: str = DEFAULT_VOICE,
    output_path: Path | None = None,
) -> Path:
    """Generate voiceover audio from text segments.

    Each segment is a dict with keys:
        - ``text`` (str): The text to speak.
        - ``duration_hint`` (float | None): Optional hint (currently unused by edge-tts).

    If there is only one segment, the audio is generated directly.
    For multiple segments, each is generated separately and concatenated
    using FFmpeg (if available) or returned as individual files in a directory.

    Returns:
        Path to the output MP3 file (single or concatenated).
    """
    if not text_segments:
        raise ValueError("text_segments must not be empty")

    # Single segment — simple case
    if len(text_segments) == 1:
        return await generate_single_audio(text_segments[0]["text"], voice=voice, output_path=output_path)

    # Multiple segments — generate individually, then concatenate
    if output_path is None:
        output_path = TTS_OUTPUT_DIR / f"tts_{uuid4().hex[:12]}.mp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmpdir = Path(tempfile.mkdtemp(prefix="tts_segments_"))
    try:
        segment_paths: list[Path] = []
        for i, seg in enumerate(text_segments):
            seg_path = tmpdir / f"seg_{i:03d}.mp3"
            await generate_single_audio(seg["text"], voice=voice, output_path=seg_path)
            segment_paths.append(seg_path)

        # Try FFmpeg concatenation
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            concat_list = tmpdir / "concat.txt"
            concat_list.write_text(
                "\n".join(f"file '{p}'" for p in segment_paths),
                encoding="utf-8",
            )
            proc = await asyncio.create_subprocess_exec(
                ffmpeg_bin,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(output_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning("FFmpeg concat failed: %s", stderr.decode(errors="replace"))
                # Fallback: return first segment
                shutil.copy2(segment_paths[0], output_path)
            else:
                logger.info(
                    "TTS voiceover concatenated: %d segments -> %s",
                    len(segment_paths),
                    output_path.name,
                )
        else:
            # No FFmpeg — concatenate raw MP3 bytes (works for MP3 streams)
            logger.info("FFmpeg not found, using raw MP3 concatenation")
            with open(output_path, "wb") as out_f:
                for seg_p in segment_paths:
                    out_f.write(seg_p.read_bytes())
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return output_path


def extract_voiceover_segments(scenario_text: str) -> list[dict]:
    """Parse scenario text to extract voiceover segments.

    Looks for patterns like:
    - "Закадровый голос: ..."
    - "Голос за кадром: ..."
    - Frame-by-frame voiceover text ("Кадр N ... Текст: ...")

    Returns:
        List of dicts with ``text`` and ``duration_hint`` keys.
    """
    segments: list[str] = []

    # Try voiceover patterns first
    for pattern in _VOICEOVER_PATTERNS:
        matches = pattern.findall(scenario_text)
        if matches:
            segments.extend(m.strip() for m in matches if m.strip())

    # Try frame-based patterns
    if not segments:
        matches = _FRAME_TEXT_PATTERN.findall(scenario_text)
        segments.extend(m.strip() for m in matches if m.strip())

    return [{"text": seg, "duration_hint": None} for seg in segments]


async def list_available_voices(language: str = "ru") -> list[dict]:
    """List available voices for the given language.

    Returns:
        List of dicts with voice metadata (Name, ShortName, Gender, Locale).
    """
    import edge_tts

    all_voices = await edge_tts.list_voices()
    filtered = [
        {
            "name": v["Name"],
            "short_name": v["ShortName"],
            "gender": v["Gender"],
            "locale": v["Locale"],
        }
        for v in all_voices
        if v.get("Locale", "").lower().startswith(language.lower())
    ]
    return filtered
