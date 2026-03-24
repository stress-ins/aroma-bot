"""CLI interface for video_grader."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# ANSI colors
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video_grader",
        description="AI-powered video color correction using Claude Vision",
    )
    parser.add_argument("-i", "--input", required=False, help="Input video file path")
    parser.add_argument("--config", help="JSON config file path")
    parser.add_argument("-o", "--output", default="", help="Output video file path")

    # Frame extraction
    parser.add_argument("--frame-count", type=int, default=6, help="Number of frames to extract (default: 6)")
    parser.add_argument("--frame-strategy", default="smart", choices=["smart", "uniform", "manual"])
    parser.add_argument("--frame-timestamps", nargs="*", type=float, help="Manual timestamps (seconds)")

    # Style
    parser.add_argument("--style", default="warm_natural",
                        choices=["warm_natural", "luxury_dark", "fresh_light", "moody_cinematic", "custom"])
    parser.add_argument("--style-description", default="", help="Custom style description")
    parser.add_argument("--context", default="", help="Additional context (lighting, camera, platform)")

    # Claude
    parser.add_argument("--model", default="claude-sonnet-4-5-20250514", help="Claude model")
    parser.add_argument("--api-key", default="", help="Anthropic API key (or use ANTHROPIC_API_KEY env)")

    # Encoding
    parser.add_argument("--codec", default="libx264")
    parser.add_argument("--preset", default="fast", choices=["ultrafast", "fast", "medium", "slow"])
    parser.add_argument("--crf", type=int, default=20)

    # Session
    parser.add_argument("--auto-apply", action="store_true", help="Apply first recommendation without asking")
    parser.add_argument("--no-report", action="store_true", help="Skip saving report files")
    parser.add_argument("--json-output", action="store_true", help="Output result as JSON")
    parser.add_argument("--pre-process", action="store_true",
                        help="Run video_processor first (clean pauses), then grade")

    # Logging
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    return parser


def _print_analysis(analysis):
    """Print formatted analysis to console."""
    from bot.services.video_grader.config import STYLE_LABELS

    print(f"\n{CYAN}{'━' * 50}")
    print(f"  VIDEO ANALYSIS")
    print(f"{'━' * 50}{RESET}\n")

    print(f"{BOLD}OVERALL{RESET}")
    print(f"  {analysis.overall_assessment}\n")

    if analysis.mood_tags:
        print(f"{BOLD}CURRENT MOOD{RESET}   {' · '.join(analysis.mood_tags)}")
    if analysis.target_mood_tags:
        print(f"{BOLD}TARGET MOOD{RESET}    {' · '.join(analysis.target_mood_tags)}")
    print()

    if analysis.dominant_issues:
        print(f"{BOLD}ISSUES{RESET}")
        for i, iss in enumerate(analysis.dominant_issues, 1):
            print(f"  {i}. {iss}")
        print()

    if analysis.per_frame:
        print(f"{BOLD}FRAMES{RESET}")
        for pf in analysis.per_frame:
            notes = pf.notes[:60] + "…" if len(pf.notes) > 60 else pf.notes
            print(f"  #{pf.frame_index}  {pf.timestamp_str}  {notes}")
        print()

    if analysis.recommendations:
        print(f"{BOLD}RECOMMENDATIONS{RESET}")
        prio_color = {"high": RED, "medium": YELLOW, "low": DIM}
        for i, r in enumerate(analysis.recommendations, 1):
            c = prio_color.get(r.priority, "")
            print(f"  {i}. {c}[{r.priority.upper():>6}]{RESET}  {r.parameter:<16} {r.ffmpeg_filter}")
        print()

    if analysis.ffmpeg_vf_string:
        print(f"{BOLD}PROPOSED VF STRING{RESET}")
        print(f"  {GREEN}{analysis.ffmpeg_vf_string}{RESET}\n")

    print(f"{DIM}Confidence: {analysis.confidence:.0%}{RESET}\n")


def _interactive_menu():
    """Show interactive menu and return choice."""
    print(f"{CYAN}{'━' * 50}")
    print(f"  WHAT DO YOU WANT TO DO?")
    print(f"{'━' * 50}{RESET}")
    print("  [1] Apply all recommendations")
    print("  [2] Apply selected  (e.g. 1,3,5)")
    print("  [3] Enter custom filters manually")
    print("  [4] Change target style")
    print("  [5] Re-analyze with comment")
    print("  [6] Skip — keep original")
    print("  [q] Quit")
    return input(f"\n{YELLOW}>{RESET} ").strip()


async def _run(args) -> int:
    from bot.services.video_grader.config import GraderConfig
    from bot.services.video_grader.frame_extractor import extract_frames_async
    from bot.services.video_grader.vision_analyzer import analyze_frames_async
    from bot.services.video_grader.grade_engine import apply_grade_async
    from bot.services.video_grader.report import save_report
    from bot.services.video_grader.config import SessionResult, IterationResult

    config = GraderConfig(
        input_file=args.input,
        output_file=args.output,
        frame_count=args.frame_count,
        frame_strategy=args.frame_strategy,
        frame_timestamps=args.frame_timestamps or [],
        target_style=args.style,
        target_style_description=args.style_description,
        additional_context=args.context,
        claude_model=args.model,
        anthropic_api_key=args.api_key,
        video_codec=args.codec,
        preset=args.preset,
        crf=args.crf,
        auto_apply=args.auto_apply,
        save_report=not args.no_report,
    )

    start = time.monotonic()
    iterations = []

    # Pre-process if requested
    if args.pre_process:
        print(f"{CYAN}Pre-processing with video_processor...{RESET}")
        from bot.services.video_processor.config import ProcessorConfig
        from bot.services.video_processor.processor import process
        loop = asyncio.get_running_loop()
        p = Path(config.input_file)
        pre_output = str(p.with_stem(p.stem + "_clean"))
        proc_config = ProcessorConfig(input_file=config.input_file, output_path=str(p.parent))
        proc_result = await loop.run_in_executor(None, process, proc_config)
        if proc_result.output_files:
            config.input_file = proc_result.output_files[0]
            print(f"{GREEN}✓ Pre-processed: {config.input_file}{RESET}\n")

    # Extract frames
    print(f"{CYAN}Extracting {config.frame_count} reference frames...{RESET}", end="", flush=True)
    t0 = time.monotonic()
    frames = await extract_frames_async(config)
    print(f"  {GREEN}done{RESET} ({time.monotonic() - t0:.1f}s)")

    for f in frames:
        bar = "▓" * int(f.brightness * 7) + "░" * (7 - int(f.brightness * 7))
        print(f"  #{f.index}  {f.timestamp_str}  {bar} {f.brightness:.0%}  {f.scene_type}")

    # Analysis loop
    analysis = None
    for iteration in range(1, config.max_iterations + 1):
        print(f"\n{CYAN}Analyzing with Claude Vision...{RESET}", end="", flush=True)
        t0 = time.monotonic()
        analysis = await analyze_frames_async(
            frames, config,
            previous_analysis=analysis if iteration > 1 else None,
        )
        print(f"  {GREEN}done{RESET} ({time.monotonic() - t0:.1f}s)")

        _print_analysis(analysis)

        if config.auto_apply:
            choice = "1"
        else:
            choice = _interactive_menu()

        if choice == "1":
            vf = analysis.ffmpeg_vf_string or ",".join(r.ffmpeg_filter for r in analysis.recommendations if r.ffmpeg_filter)
            if not vf:
                print(f"{RED}No filters to apply.{RESET}")
                continue
            print(f"\n{CYAN}Applying grade...{RESET}", end="", flush=True)
            t0 = time.monotonic()
            result = await apply_grade_async(config, vf, config.output_file)
            print(f"  {GREEN}done{RESET} ({time.monotonic() - t0:.1f}s)")
            print(f"\n{GREEN}✓ Output: {result.output_file}{RESET}")

            iterations.append(IterationResult(
                iteration=iteration, analysis=analysis, user_choice="apply_all",
                applied_filters=[r.ffmpeg_filter for r in analysis.recommendations],
                output_file=result.output_file, user_comment="",
            ))
            break

        elif choice == "2":
            indices_str = input("Enter recommendation numbers (comma-separated): ").strip()
            indices = [int(x.strip()) - 1 for x in indices_str.split(",") if x.strip().isdigit()]
            filters = [analysis.recommendations[i].ffmpeg_filter for i in indices if 0 <= i < len(analysis.recommendations)]
            if not filters:
                print(f"{RED}No valid filters selected.{RESET}")
                continue
            vf = ",".join(filters)
            print(f"\n{CYAN}Applying selected filters...{RESET}", end="", flush=True)
            result = await apply_grade_async(config, vf, config.output_file)
            print(f"  {GREEN}done{RESET}")
            print(f"\n{GREEN}✓ Output: {result.output_file}{RESET}")
            iterations.append(IterationResult(
                iteration=iteration, analysis=analysis,
                user_choice=f"selected:{indices_str}", applied_filters=filters,
                output_file=result.output_file, user_comment="",
            ))
            break

        elif choice == "3":
            custom_vf = input("Enter FFmpeg -vf string: ").strip()
            if not custom_vf:
                continue
            result = await apply_grade_async(config, custom_vf, config.output_file)
            print(f"\n{GREEN}✓ Output: {result.output_file}{RESET}")
            iterations.append(IterationResult(
                iteration=iteration, analysis=analysis,
                user_choice="custom", applied_filters=[custom_vf],
                output_file=result.output_file, user_comment="",
            ))
            break

        elif choice == "5":
            comment = input(f"{YELLOW}Что нужно изменить? > {RESET}").strip()
            iterations.append(IterationResult(
                iteration=iteration, analysis=analysis,
                user_choice="reanalyze", applied_filters=[], output_file=None,
                user_comment=comment,
            ))
            config.additional_context += f"\n{comment}"
            continue

        elif choice in ("6", "q"):
            break

    elapsed = time.monotonic() - start

    session_result = SessionResult(
        input_file=config.input_file,
        output_file=iterations[-1].output_file if iterations and iterations[-1].output_file else None,
        frames=frames,
        iterations=iterations,
        final_vf_string=analysis.ffmpeg_vf_string if analysis else None,
        success=bool(iterations and iterations[-1].output_file),
        total_time_seconds=elapsed,
    )

    if config.save_report and iterations:
        report_path = save_report(session_result, config)
        print(f"{GREEN}✓ Report: {report_path}{RESET}")

    if args.json_output:
        print(json.dumps({
            "input_file": session_result.input_file,
            "output_file": session_result.output_file,
            "success": session_result.success,
            "total_time_seconds": round(session_result.total_time_seconds, 1),
            "final_vf_string": session_result.final_vf_string,
        }))

    return 0 if session_result.success else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Check ffmpeg
    import shutil
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print(f"{RED}Error: ffmpeg and ffprobe must be in PATH{RESET}", file=sys.stderr)
        return 1

    # Load config from file or args
    if args.config:
        with open(args.config) as f:
            data = json.load(f)
        from bot.services.video_grader.config import GraderConfig
        # Merge CLI args over config file
        for k, v in vars(args).items():
            if k != "config" and v is not None:
                data.setdefault(k, v)
        args.input = data.get("input_file", args.input)
        args.output = data.get("output_file", args.output or "")

    if not args.input:
        parser.error("--input is required (or use --config)")

    if not Path(args.input).exists():
        print(f"{RED}Error: file not found: {args.input}{RESET}", file=sys.stderr)
        return 1

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
