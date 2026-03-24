"""Analyze video frames with Claude Vision for color correction recommendations."""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

import anthropic

from bot.services.video_grader.config import (
    STYLE_LABELS,
    FrameAnalysis,
    FrameInfo,
    GraderConfig,
    Recommendation,
    VideoAnalysis,
)

logger = logging.getLogger(__name__)


class VisionAnalysisError(RuntimeError):
    pass


SYSTEM_PROMPT = """You are a professional colorist specializing in social media video content for wellness, aromatherapy, and lifestyle brands.

You will analyze multiple reference frames from the same video and provide precise, actionable color correction recommendations with FFmpeg filters.

Rules:
- Analyze ALL frames together to understand lighting consistency across the video
- Note differences between frames (e.g., color shift in certain moments)
- Recommend corrections that work well across ALL frames, not just one
- Keep FFmpeg filters practical and ready to paste into terminal
- Respond ONLY with valid JSON matching the exact schema below
- No markdown, no backticks, no preamble
- All text in Russian

Available FFmpeg filters to use:
  eq=brightness=X:contrast=X:saturation=X:gamma=X
  colorbalance=rs=X:gs=X:bs=X:rm=X:gm=X:bm=X:rh=X:gh=X:bh=X
  curves=r='points':g='points':b='points'
  hue=s=X:h=X
  vignette=PI/X:eval=init
  unsharp=5:5:X:3:3:0
  colorchannelmixer=X:X:X:0:X:X:X:0:X:X:X:0

JSON schema:
{
  "overall_assessment": "string — общая оценка",
  "dominant_issues": ["issue1", "issue2"],
  "mood_tags": ["current_mood1", "current_mood2"],
  "target_mood_tags": ["target_mood1", "target_mood2"],
  "per_frame": [
    {
      "frame_index": 0,
      "timestamp_str": "00:00:05",
      "issues": ["issue1"],
      "notes": "string"
    }
  ],
  "recommendations": [
    {
      "parameter": "brightness",
      "current_state": "string",
      "suggestion": "string",
      "ffmpeg_filter": "eq=brightness=-0.08",
      "priority": "high"
    }
  ],
  "ffmpeg_vf_string": "complete -vf filter chain",
  "ffmpeg_full_command": "ffmpeg -i input.mp4 -vf \\"FILTERS\\" -c:v libx264 -preset fast -crf 20 output.mp4",
  "confidence": 0.85
}"""


def _load_frame_base64(filepath: str) -> str:
    """Load image file and return base64-encoded string."""
    with open(filepath, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("ascii")


def _media_type(filepath: str) -> str:
    """Determine media type from file extension."""
    ext = Path(filepath).suffix.lower()
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(
        ext.lstrip("."), "image/jpeg"
    )


def analyze_frames(
    frames: list[FrameInfo],
    config: GraderConfig,
    *,
    previous_analysis: VideoAnalysis | None = None,
    user_comment: str = "",
) -> VideoAnalysis:
    """Send frames to Claude Vision and get color correction recommendations."""
    api_key = config.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise VisionAnalysisError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    # Build user message with all frames
    content: list[dict] = []

    # Add text context
    style_label = STYLE_LABELS.get(config.target_style, config.target_style)
    text_parts = [f"Целевой стиль: {style_label}"]
    if config.target_style == "custom" and config.target_style_description:
        text_parts.append(f"Описание стиля: {config.target_style_description}")
    if config.additional_context:
        text_parts.append(f"Контекст: {config.additional_context}")

    timestamps = ", ".join(f.timestamp_str for f in frames)
    text_parts.append(
        f"\nАнализирую {len(frames)} референсных кадров из одного видео.\n"
        f"Временные метки: {timestamps}\n\n"
        "Проанализируй цветовое качество по всем кадрам и дай единые рекомендации по коррекции."
    )

    if previous_analysis and user_comment:
        text_parts.append(
            f"\n\nПредыдущий анализ давал такие рекомендации:\n"
            f"vf_string: {previous_analysis.ffmpeg_vf_string}\n"
            f"Комментарий пользователя: {user_comment}\n"
            "Учти этот фидбек в новых рекомендациях."
        )

    content.append({"type": "text", "text": "\n".join(text_parts)})

    # Add frames as images
    for frame in frames:
        if not Path(frame.filepath).exists():
            logger.warning("Frame file missing: %s", frame.filepath)
            continue
        b64 = _load_frame_base64(frame.filepath)
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _media_type(frame.filepath),
                "data": b64,
            },
        })
        content.append({
            "type": "text",
            "text": f"Кадр #{frame.index} — {frame.timestamp_str} ({frame.scene_type}, яркость {frame.brightness:.0%})",
        })

    logger.info("Sending %d frames to Claude Vision (%s)...", len(frames), config.claude_model)

    # Call Claude API
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=config.claude_model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            break
        except (anthropic.RateLimitError, anthropic.InternalServerError) as exc:
            if attempt == 0:
                logger.warning("Claude API error, retrying: %s", exc)
                import time
                time.sleep(3)
            else:
                raise VisionAnalysisError(f"Claude API error after retry: {exc}") from exc

    # Parse response
    raw_text = response.content[0].text.strip()

    # Strip markdown code blocks if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Claude returned invalid JSON: %s...", raw_text[:200])
        raise VisionAnalysisError(f"Invalid JSON from Claude: {exc}") from exc

    # Build VideoAnalysis
    per_frame = [
        FrameAnalysis(
            frame_index=pf.get("frame_index", i),
            timestamp_str=pf.get("timestamp_str", ""),
            issues=pf.get("issues", []),
            notes=pf.get("notes", ""),
        )
        for i, pf in enumerate(data.get("per_frame", []))
    ]

    recommendations = [
        Recommendation(
            parameter=r.get("parameter", ""),
            current_state=r.get("current_state", ""),
            suggestion=r.get("suggestion", ""),
            ffmpeg_filter=r.get("ffmpeg_filter", ""),
            priority=r.get("priority", "medium"),
        )
        for r in data.get("recommendations", [])
    ]

    analysis = VideoAnalysis(
        overall_assessment=data.get("overall_assessment", ""),
        dominant_issues=data.get("dominant_issues", []),
        mood_tags=data.get("mood_tags", []),
        target_mood_tags=data.get("target_mood_tags", []),
        per_frame=per_frame,
        recommendations=recommendations,
        ffmpeg_vf_string=data.get("ffmpeg_vf_string", ""),
        ffmpeg_full_command=data.get("ffmpeg_full_command", ""),
        confidence=float(data.get("confidence", 0.5)),
    )

    logger.info(
        "Analysis complete: %d recommendations, confidence %.0f%%",
        len(recommendations),
        analysis.confidence * 100,
    )
    return analysis


async def analyze_frames_async(
    frames: list[FrameInfo],
    config: GraderConfig,
    **kwargs,
) -> VideoAnalysis:
    """Async wrapper around analyze_frames."""
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: analyze_frames(frames, config, **kwargs)
    )
