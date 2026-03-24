"""Allow running as `python -m bot.services.video_grader`."""
import sys
from bot.services.video_grader.cli import main

sys.exit(main())
