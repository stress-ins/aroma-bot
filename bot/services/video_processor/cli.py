"""CLI interface for video_processor."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video_processor",
        description="Remove silences and filler words from video recordings.",
    )

    parser.add_argument(
        "--input", "-i",
        required=False,
        help="Path to input video file",
    )
    parser.add_argument(
        "--config",
        help="Path to JSON config file (overrides all other args)",
    )

    # Output
    parser.add_argument(
        "--output", "-o",
        default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["single", "split"],
        default="single",
        help="Output mode: 'single' merged file or 'split' clips (default: single)",
    )

    # Silence detection
    parser.add_argument(
        "--min-pause-duration",
        type=float,
        default=0.4,
        help="Cut silences longer than N seconds (default: 0.4)",
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.05,
        help="Audio buffer around each speech segment in seconds (default: 0.05)",
    )
    parser.add_argument(
        "--silence-threshold",
        type=float,
        default=-35.0,
        help="Silence detection threshold in dB (default: -35.0)",
    )

    # Whisper
    parser.add_argument(
        "--whisper",
        action="store_true",
        default=False,
        help="Enable Whisper STT for filler word detection (requires openai-whisper)",
    )
    parser.add_argument(
        "--no-whisper",
        action="store_true",
        help="Disable Whisper, use silencedetect only (default)",
    )
    parser.add_argument(
        "--whisper-model",
        default="tiny",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size (default: tiny)",
    )
    parser.add_argument(
        "--whisper-language",
        default="ru",
        help="Language for Whisper transcription (default: ru)",
    )

    # Filler words
    parser.add_argument(
        "--filler-words",
        nargs="*",
        help="Custom filler words list (space-separated)",
    )

    # Transitions (single mode)
    parser.add_argument(
        "--transitions",
        action="store_true",
        default=False,
        help="Enable xfade transitions between segments (single mode only)",
    )
    parser.add_argument(
        "--transition-type",
        default="fade",
        help="Transition type: fade, dissolve, wipeleft, etc. (default: fade)",
    )
    parser.add_argument(
        "--transition-duration",
        type=float,
        default=0.3,
        help="Transition duration in seconds (default: 0.3)",
    )

    # Split mode
    parser.add_argument(
        "--split-min-duration",
        type=float,
        default=1.5,
        help="Minimum clip duration in split mode (default: 1.5s)",
    )
    parser.add_argument(
        "--split-max-duration",
        type=float,
        default=30.0,
        help="Maximum clip duration in split mode (default: 30.0s)",
    )
    parser.add_argument(
        "--split-naming",
        default="clip_{:03d}.mp4",
        help="Clip naming pattern for split mode (default: clip_{:03d}.mp4)",
    )

    # Encoding
    parser.add_argument(
        "--video-codec",
        default="libx264",
        help="Video codec (default: libx264)",
    )
    parser.add_argument(
        "--audio-codec",
        default="aac",
        help="Audio codec (default: aac)",
    )
    parser.add_argument(
        "--preset",
        default="fast",
        choices=["ultrafast", "fast", "medium", "slow"],
        help="Encoding preset (default: fast)",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        help="Constant Rate Factor 18-28 (default: 23, lower = better quality)",
    )

    # Logging
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from bot.services.video_processor.config import ProcessorConfig
    from bot.services.video_processor.processor import process

    # Build config from JSON file or CLI args
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: config file not found: {config_path}", file=sys.stderr)
            return 1
        with open(config_path) as f:
            data = json.load(f)
        config = ProcessorConfig(**data)
    else:
        if not args.input:
            parser.error("--input is required (or use --config)")

        use_whisper = args.whisper and not args.no_whisper
        config = ProcessorConfig(
            input_file=args.input,
            output_path=args.output,
            mode=args.mode,
            min_pause_duration=args.min_pause_duration,
            padding=args.padding,
            silence_threshold_db=args.silence_threshold,
            use_whisper=use_whisper,
            whisper_model=args.whisper_model,
            whisper_language=args.whisper_language,
            transitions_enabled=args.transitions,
            transition_type=args.transition_type,
            transition_duration=args.transition_duration,
            split_min_clip_duration=args.split_min_duration,
            split_max_clip_duration=args.split_max_duration,
            split_naming_pattern=args.split_naming,
            video_codec=args.video_codec,
            audio_codec=args.audio_codec,
            preset=args.preset,
            crf=args.crf,
        )

        if args.filler_words is not None:
            config.filler_words = args.filler_words

    try:
        result = process(config)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Print summary
    _print_summary(result)
    return 0


def _print_summary(result) -> None:  # noqa: ANN001
    """Print human-readable summary to stdout."""
    from bot.services.video_processor.processor import _format_duration

    if result.mode == "single":
        print(f"\n  Done. Output: {result.output_files[0]}")
    else:
        print(f"\n  Done. {result.clip_count} clips saved to {Path(result.output_files[0]).parent}/")
        for f in result.output_files:
            print(f"    {Path(f).name}")

    print(
        f"  Input: {_format_duration(result.total_input_duration)} "
        f"-> Output: {_format_duration(result.total_output_duration)} "
        f"(removed {_format_duration(result.removed_duration)} of silence/fillers)",
    )


if __name__ == "__main__":
    sys.exit(main())
