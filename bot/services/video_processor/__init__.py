"""Video processor — remove silences and filler words from raw video."""

from bot.services.video_processor.config import ProcessorConfig
from bot.services.video_processor.processor import ProcessResult, process

__all__ = ["ProcessorConfig", "ProcessResult", "process"]
