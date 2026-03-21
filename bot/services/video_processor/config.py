"""ProcessorConfig — all settings for the video processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ProcessorConfig:
    """Configuration for a single video processing run."""

    # --- Input / output ---
    input_file: str  # path to source video
    output_path: str = "./output"  # folder for results
    mode: Literal["single", "split"] = "single"

    # --- Silence / pause filtering ---
    min_pause_duration: float = 0.4  # silences longer than this are cut (seconds)
    padding: float = 0.05  # buffer kept around each speech segment (seconds)
    silence_threshold_db: float = -35.0  # silencedetect noise threshold

    # --- Filler words (used only when Whisper is enabled) ---
    filler_words: list[str] = field(default_factory=lambda: [
        "ну", "вот", "это", "как бы", "короче", "собственно",
        "типа", "значит", "буквально", "реально", "вообще",
    ])

    # --- Whisper STT (optional, disabled by default) ---
    use_whisper: bool = False
    whisper_model: str = "tiny"  # tiny | base | small | medium | large-v3
    whisper_language: str = "ru"

    # --- Transitions (mode="single" only) ---
    transitions_enabled: bool = False
    transition_type: str = "fade"
    transition_duration: float = 0.3

    # --- Split mode (mode="split" only) ---
    split_min_clip_duration: float = 1.5  # drop clips shorter than this
    split_max_clip_duration: float = 30.0  # max seconds per clip
    split_naming_pattern: str = "clip_{:03d}.mp4"

    # --- Encoding ---
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    preset: str = "fast"
    crf: int = 23
