"""Interactive grading session — orchestrates frame extraction, analysis, and grading."""
from __future__ import annotations

import logging
import time

from bot.services.video_grader.config import (
    GraderConfig,
    IterationResult,
    SessionResult,
    VideoAnalysis,
)
from bot.services.video_grader.frame_extractor import extract_frames_async
from bot.services.video_grader.grade_engine import apply_grade_async
from bot.services.video_grader.report import save_report
from bot.services.video_grader.vision_analyzer import analyze_frames_async

logger = logging.getLogger(__name__)


class GraderSession:
    """Non-interactive async session for web integration.

    For CLI interactive mode, see cli.py.
    This class runs the full pipeline: extract → analyze → apply.
    """

    def __init__(self, config: GraderConfig):
        self.config = config
        self.frames = []
        self.iterations: list[IterationResult] = []
        self._start_time = 0.0

    async def run_analysis(self) -> VideoAnalysis:
        """Extract frames and run Claude Vision analysis."""
        self._start_time = time.monotonic()

        # Extract frames
        self.frames = await extract_frames_async(self.config)
        logger.info("Extracted %d frames", len(self.frames))

        # Analyze
        analysis = await analyze_frames_async(self.frames, self.config)
        return analysis

    async def apply_all(
        self,
        analysis: VideoAnalysis,
        output_file: str = "",
    ) -> SessionResult:
        """Apply all recommendations from analysis."""
        vf_string = analysis.ffmpeg_vf_string
        if not vf_string:
            # Build from individual recommendations
            filters = [r.ffmpeg_filter for r in analysis.recommendations if r.ffmpeg_filter]
            vf_string = ",".join(filters)

        if not vf_string:
            return self._build_result(None, None, analysis, "skip")

        result = await apply_grade_async(self.config, vf_string, output_file)

        iteration = IterationResult(
            iteration=len(self.iterations) + 1,
            analysis=analysis,
            user_choice="apply_all",
            applied_filters=[r.ffmpeg_filter for r in analysis.recommendations],
            output_file=result.output_file,
            user_comment="",
        )
        self.iterations.append(iteration)

        session_result = self._build_result(
            result.output_file, vf_string, analysis, "apply_all",
        )

        if self.config.save_report:
            save_report(session_result, self.config)

        return session_result

    async def apply_selected(
        self,
        analysis: VideoAnalysis,
        indices: list[int],
        output_file: str = "",
    ) -> SessionResult:
        """Apply selected recommendations by index."""
        filters = []
        for i in indices:
            if 0 <= i < len(analysis.recommendations):
                f = analysis.recommendations[i].ffmpeg_filter
                if f:
                    filters.append(f)

        if not filters:
            return self._build_result(None, None, analysis, "skip")

        vf_string = ",".join(filters)
        result = await apply_grade_async(self.config, vf_string, output_file)

        iteration = IterationResult(
            iteration=len(self.iterations) + 1,
            analysis=analysis,
            user_choice=f"selected:{','.join(str(i) for i in indices)}",
            applied_filters=filters,
            output_file=result.output_file,
            user_comment="",
        )
        self.iterations.append(iteration)

        session_result = self._build_result(
            result.output_file, vf_string, analysis, "apply_selected",
        )

        if self.config.save_report:
            save_report(session_result, self.config)

        return session_result

    async def reanalyze(
        self,
        comment: str = "",
        previous_analysis: VideoAnalysis | None = None,
    ) -> VideoAnalysis:
        """Re-run analysis with user feedback."""
        if comment:
            self.config.additional_context = (
                (self.config.additional_context or "") + f"\n\nПользователь: {comment}"
            ).strip()

        analysis = await analyze_frames_async(
            self.frames,
            self.config,
            previous_analysis=previous_analysis,
            user_comment=comment,
        )
        return analysis

    def _build_result(
        self,
        output_file: str | None,
        vf_string: str | None,
        analysis: VideoAnalysis,
        choice: str,
    ) -> SessionResult:
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        return SessionResult(
            input_file=self.config.input_file,
            output_file=output_file,
            frames=self.frames,
            iterations=self.iterations,
            final_vf_string=vf_string,
            success=output_file is not None,
            total_time_seconds=elapsed,
        )
