"""Video Grader configuration."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GraderConfig:
    # --- Input ---
    input_file: str = ""

    # --- Frame extraction ---
    frame_count: int = 6
    frame_strategy: str = "smart"  # smart | uniform | manual
    frame_timestamps: list[float] = field(default_factory=list)
    frame_output_dir: str = "./grader_frames"
    frame_format: str = "jpg"
    frame_quality: int = 90

    # --- Claude Vision analysis ---
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5-20250514"
    target_style: str = "warm_natural"
    # warm_natural | luxury_dark | fresh_light | moody_cinematic | custom
    target_style_description: str = ""
    additional_context: str = ""

    # --- Grade application ---
    output_file: str = ""
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    preset: str = "fast"
    crf: int = 20

    # --- Session ---
    max_iterations: int = 5
    auto_apply: bool = False
    save_report: bool = True
    report_path: str = ""


STYLE_LABELS = {
    "warm_natural": "Тёплый натуральный (аромаэксперт, wellness)",
    "luxury_dark": "Тёмный люкс (премиум, moody)",
    "fresh_light": "Свежий светлый (минимализм, чистота)",
    "moody_cinematic": "Кинематографичный (глубокие тени, контраст)",
    "custom": "Свой стиль",
}


@dataclass
class FrameInfo:
    index: int
    timestamp: float
    timestamp_str: str
    filepath: str
    scene_type: str  # intro | mid | outro | bright | manual
    brightness: float  # 0.0–1.0


@dataclass
class FrameAnalysis:
    frame_index: int
    timestamp_str: str
    issues: list[str]
    notes: str


@dataclass
class Recommendation:
    parameter: str
    current_state: str
    suggestion: str
    ffmpeg_filter: str
    priority: str  # high | medium | low


@dataclass
class VideoAnalysis:
    overall_assessment: str
    dominant_issues: list[str]
    mood_tags: list[str]
    target_mood_tags: list[str]
    per_frame: list[FrameAnalysis]
    recommendations: list[Recommendation]
    ffmpeg_vf_string: str
    ffmpeg_full_command: str
    confidence: float


@dataclass
class GradeResult:
    success: bool
    output_file: str
    input_duration: float
    output_duration: float
    ffmpeg_command: str
    stderr: str


@dataclass
class IterationResult:
    iteration: int
    analysis: VideoAnalysis
    user_choice: str
    applied_filters: list[str]
    output_file: str | None
    user_comment: str


@dataclass
class SessionResult:
    input_file: str
    output_file: str | None
    frames: list[FrameInfo]
    iterations: list[IterationResult]
    final_vf_string: str | None
    success: bool
    total_time_seconds: float
