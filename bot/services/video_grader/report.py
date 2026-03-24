"""Save grading session report in JSON and Markdown."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from bot.services.video_grader.config import GraderConfig, SessionResult

logger = logging.getLogger(__name__)


def save_report(result: SessionResult, config: GraderConfig) -> str:
    """Save session report as JSON and Markdown. Returns JSON path."""
    base = Path(config.input_file).stem
    report_dir = Path(config.report_path).parent if config.report_path else Path(config.input_file).parent
    report_dir.mkdir(parents=True, exist_ok=True)

    json_path = config.report_path or str(report_dir / f"{base}_grader_report.json")
    md_path = str(Path(json_path).with_suffix(".md"))

    # JSON report
    report_data = {
        "input_file": result.input_file,
        "output_file": result.output_file,
        "target_style": config.target_style,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_iterations": len(result.iterations),
        "frames_analyzed": len(result.frames),
        "final_ffmpeg_command": result.final_vf_string,
        "success": result.success,
        "total_time_seconds": round(result.total_time_seconds, 1),
        "iterations": [
            {
                "iteration": it.iteration,
                "overall_assessment": it.analysis.overall_assessment,
                "recommendations": [
                    {
                        "parameter": r.parameter,
                        "ffmpeg_filter": r.ffmpeg_filter,
                        "priority": r.priority,
                    }
                    for r in it.analysis.recommendations
                ],
                "applied_filters": it.applied_filters,
                "user_comment": it.user_comment,
            }
            for it in result.iterations
        ],
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    # Markdown report
    lines = [
        f"# Video Grader Report",
        f"",
        f"**Input:** `{result.input_file}`",
        f"**Output:** `{result.output_file or 'N/A'}`",
        f"**Style:** {config.target_style}",
        f"**Iterations:** {len(result.iterations)}",
        f"**Time:** {result.total_time_seconds:.1f}s",
        f"",
    ]

    # Frames
    lines.append("## Frames\n")
    for f in result.frames:
        lines.append(f"- #{f.index} `{f.timestamp_str}` — {f.scene_type}, brightness {f.brightness:.0%}")

    # Iterations
    for it in result.iterations:
        lines.append(f"\n## Iteration {it.iteration}\n")
        lines.append(f"**Assessment:** {it.analysis.overall_assessment}\n")

        if it.analysis.dominant_issues:
            lines.append("**Issues:**")
            for iss in it.analysis.dominant_issues:
                lines.append(f"- {iss}")

        if it.analysis.recommendations:
            lines.append("\n**Recommendations:**")
            for r in it.analysis.recommendations:
                lines.append(f"- [{r.priority.upper()}] {r.parameter}: `{r.ffmpeg_filter}`")

        if it.applied_filters:
            lines.append(f"\n**Applied:** `{', '.join(it.applied_filters)}`")
        if it.user_comment:
            lines.append(f"\n**User comment:** {it.user_comment}")

    # Final command
    if result.final_vf_string:
        lines.append(f"\n## Final FFmpeg Command\n")
        lines.append(f"```bash\nffmpeg -i {result.input_file} -vf \"{result.final_vf_string}\" "
                      f"-c:v {config.video_codec} -preset {config.preset} -crf {config.crf} {result.output_file}\n```")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Reports saved: %s, %s", json_path, md_path)
    return json_path
