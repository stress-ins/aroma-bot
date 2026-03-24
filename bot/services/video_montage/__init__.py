"""Video Montage — auto-editing pipeline for cleaned videos.

Pipeline: cleaned video + keep_intervals + script + AI frames → publish-ready video.
Features: transitions, text overlays, background music, B-roll, beat-sync, color grading.
"""
from bot.services.video_montage.config import MontageConfig, MontageTemplate
from bot.services.video_montage.engine import run_montage

__all__ = ["MontageConfig", "MontageTemplate", "run_montage"]
