"""Video Montage configuration and templates."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MontageTemplate(str, Enum):
    MINIMAL = "minimal"        # transitions + music only
    EXPERT = "expert"          # transitions + subtitles + music
    FULL = "full"              # everything: transitions + subtitles + B-roll + music + beat-sync + color
    CUSTOM = "custom"          # manual toggle of each feature


@dataclass
class MontageConfig:
    """Configuration for auto-montage pipeline."""

    # --- Input ---
    input_video: str = ""          # path to cleaned video
    draft_id: str = ""             # reels draft ID (for fetching script, frames, etc.)
    keep_intervals: list[list[float]] = field(default_factory=list)  # [[start, end], ...]

    # --- Template ---
    template: str = "expert"       # minimal | expert | full | custom

    # --- Feature toggles (used with template=custom, or override template defaults) ---
    transitions_enabled: bool = True
    transition_type: str = "fade"  # fade | dissolve | wipeleft | slideright | circlecrop
    transition_duration: float = 0.3

    subtitles_enabled: bool = True
    subtitle_source: str = "auto"  # auto | script | video
    #   auto   — use video transcription if available, else script
    #   script — only from reels script/storyboard
    #   video  — always transcribe video audio with Whisper
    subtitle_style: str = "bottom_bar"  # bottom_bar | centered | karaoke | minimal
    subtitle_font_size: int = 28
    subtitle_color: str = "white"
    subtitle_bg_opacity: float = 0.6

    music_enabled: bool = True
    music_track: str = ""          # path to music file, or "auto" for library pick
    music_volume: float = 0.15     # 0.0–1.0 relative to speech
    music_fade_in: float = 2.0
    music_fade_out: float = 3.0

    broll_enabled: bool = False    # insert AI-generated frames between fragments
    broll_duration: float = 2.0    # seconds per B-roll insert
    broll_max_inserts: int = 3     # max B-roll clips to insert
    broll_frames: list[str] = field(default_factory=list)  # paths to B-roll images

    beat_sync_enabled: bool = False  # align cuts to music beats
    beat_tolerance: float = 0.3      # seconds tolerance for beat alignment

    audio_normalize: bool = True     # normalize speech to -16 dB LUFS
    audio_target_lufs: float = -16.0 # target loudness (Instagram standard)

    color_grade_enabled: bool = False
    color_grade_vf: str = ""        # FFmpeg -vf string from video_grader

    # --- Output ---
    output_path: str = ""
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    preset: str = "fast"
    crf: int = 20

    def apply_template(self) -> None:
        """Set feature toggles based on selected template."""
        if self.template == "minimal":
            self.transitions_enabled = True
            self.subtitles_enabled = False
            self.music_enabled = True
            self.broll_enabled = False
            self.beat_sync_enabled = False
            self.color_grade_enabled = False
        elif self.template == "expert":
            self.transitions_enabled = True
            self.subtitles_enabled = True
            self.music_enabled = True
            self.broll_enabled = False
            self.beat_sync_enabled = False
            self.color_grade_enabled = True
        elif self.template == "full":
            self.transitions_enabled = True
            self.subtitles_enabled = True
            self.music_enabled = True
            self.broll_enabled = True
            self.beat_sync_enabled = True
            self.color_grade_enabled = True
        # custom — use whatever is set


TEMPLATE_LABELS = {
    "minimal": "Минимал — переходы + музыка",
    "expert": "Эксперт — переходы + субтитры + музыка + цвет",
    "full": "Полный — всё: переходы + субтитры + B-roll + музыка + ритм + цвет",
    "custom": "Свой — ручной выбор опций",
}

TRANSITION_TYPES = {
    "fade": "Затухание",
    "dissolve": "Растворение",
    "wipeleft": "Вытеснение влево",
    "slideright": "Сдвиг вправо",
    "circlecrop": "Круговое",
}

SUBTITLE_STYLES = {
    "bottom_bar": "Полоска внизу",
    "centered": "По центру",
    "karaoke": "Караоке (подсветка слов)",
    "minimal": "Минимум (без фона)",
}


@dataclass
class MontageResult:
    """Result of montage pipeline."""
    success: bool
    output_file: str
    duration: float
    features_applied: list[str]  # which features were actually used
    ffmpeg_commands: list[str]   # commands that were executed
    error: str = ""
