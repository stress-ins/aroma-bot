"""Video Grader — AI-powered color correction for social media videos.

Uses Claude Vision to analyze reference frames and generate FFmpeg filter chains.
"""
from bot.services.video_grader.config import GraderConfig
from bot.services.video_grader.session import GraderSession

__all__ = ["GraderConfig", "GraderSession"]
