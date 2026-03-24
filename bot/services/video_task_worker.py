"""Video task worker — processes video tasks from the persistent queue.

Runs as a background asyncio task. Picks up one task at a time,
executes it, and moves to the next. Survives server restarts by
reading pending tasks from the database.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bot.services.video_task_store import (
    claim_next_task,
    complete_task,
    fail_task,
    recover_interrupted_tasks,
    update_task_progress,
)

logger = logging.getLogger(__name__)

_VIDEO_TASK_TYPES = ("clean", "compose", "grade", "montage")

# In-memory status for SSE/polling (fast reads, not persisted)
live_status: dict[str, dict] = {}
_events: dict[str, asyncio.Event] = {}
_worker_task: asyncio.Task | None = None

# Users to notify when a task for their draft completes
# {draft_id: set of telegram_user_ids}
_notify_subscribers: dict[str, set[int]] = {}


def subscribe_notification(draft_id: str, telegram_user_id: int) -> None:
    """Register user to be notified when video task completes."""
    if draft_id not in _notify_subscribers:
        _notify_subscribers[draft_id] = set()
    _notify_subscribers[draft_id].add(telegram_user_id)


async def _send_notifications(draft_id: str, task_type: str, status: str) -> None:
    """Send Telegram notification to subscribed users."""
    subscribers = _notify_subscribers.pop(draft_id, set())
    if not subscribers:
        return

    from config import settings
    import httpx

    bot_token = settings.telegram_bot_token
    if not bot_token:
        return

    task_labels = {"clean": "Очистка видео", "compose": "Сборка видео", "grade": "Цветокоррекция"}
    emoji = "\u2705" if status == "completed" else "\u274c"
    task_label = task_labels.get(task_type, task_type)
    status_label = "завершена" if status == "completed" else "не удалась"
    text = f"{emoji} {task_label} {status_label}.\n\nОткройте приложение чтобы посмотреть результат."

    async with httpx.AsyncClient(timeout=10) as client:
        for uid in subscribers:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": uid, "text": text},
                )
            except Exception:
                logger.debug("Failed to notify user %s", uid)


def notify(draft_id: str) -> None:
    """Wake up any SSE listeners for this draft."""
    evt = _events.get(draft_id)
    if evt:
        evt.set()


def get_event(draft_id: str) -> asyncio.Event:
    """Get or create an event for SSE streaming."""
    if draft_id not in _events:
        _events[draft_id] = asyncio.Event()
    return _events[draft_id]


async def _notify_admin_error(task, error_msg: str) -> None:
    """Send error details to admin via Telegram (monitoring)."""
    try:
        from config import settings
        import httpx

        bot_token = settings.telegram_bot_token
        if not bot_token:
            return

        # Try admin chat, fallback to draft creator
        admin_chat_id = getattr(settings, "admin_telegram_chat_id", "") or ""
        if not admin_chat_id:
            # Get draft creator
            try:
                from bot.services.drafts_store import get_draft
                draft = await get_draft(task.draft_id)
                if draft and draft.created_by:
                    admin_chat_id = str(draft.created_by)
            except Exception:
                pass

        if not admin_chat_id:
            logger.warning("No admin_chat_id and no draft creator — cannot send error notification")
            return

        is_oom = "rc=-9" in error_msg or "OOM" in error_msg or "killed" in error_msg
        task_labels = {"clean": "Очистка видео", "compose": "Сборка видео", "grade": "Цветокоррекция"}
        task_label = task_labels.get(task.task_type, task.task_type)
        text = (
            f"\u26a0\ufe0f {task_label} — ошибка\n\n"
            f"Draft: {task.draft_id[:8]}\n"
            f"Длительность: {task.video_duration or '?'}с\n"
            f"{'⚡ OOM (нехватка памяти)' if is_oom else 'Ошибка'}\n\n"
            f"{error_msg[:500]}"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": admin_chat_id, "text": text},
            )
            logger.info("Sent error notification to %s", admin_chat_id)
    except Exception:
        logger.debug("Failed to notify admin about video task error", exc_info=True)


async def start_worker() -> None:
    """Start the background worker. Call once at app startup."""
    global _worker_task

    try:
        # Ensure table exists (auto-create if missing)
        from db.models import VideoTaskModel, Base
        from sqlalchemy.ext.asyncio import create_async_engine
        from db.session import DATABASE_URL
        _engine = create_async_engine(DATABASE_URL, echo=False)
        async with _engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, tables=[VideoTaskModel.__table__], checkfirst=True,
                )
            )
        await _engine.dispose()

        # Reset any video tasks that were running when server died
        recovered = await recover_interrupted_tasks(task_types=_VIDEO_TASK_TYPES)
        if recovered:
            logger.info("video_worker: recovered %d interrupted tasks", recovered)
    except Exception:
        logger.warning("video_worker: could not initialize table, will retry", exc_info=True)

    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())
        logger.info("video_worker: started")


async def _worker_loop() -> None:
    """Main worker loop — picks tasks one by one."""
    while True:
        try:
            task = await claim_next_task(task_types=_VIDEO_TASK_TYPES)
            if not task:
                await asyncio.sleep(3)
                continue

            logger.info(
                "video_worker: processing %s task %s for draft %s",
                task.task_type, task.task_id, task.draft_id,
            )

            live_status[task.draft_id] = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": "running",
                "step": "preparing",
                "progress": 0,
                "video_duration": task.video_duration,
            }
            notify(task.draft_id)

            try:
                if task.task_type == "clean":
                    result = await _execute_clean(task)
                elif task.task_type == "compose":
                    result = await _execute_compose(task)
                elif task.task_type == "grade":
                    result = await _execute_grade(task)
                elif task.task_type == "montage":
                    result = await _execute_montage(task)
                else:
                    raise ValueError(f"Unknown task type: {task.task_type}")

                await complete_task(task.task_id, result=result)
                live_status[task.draft_id] = {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": "completed",
                    "step": "done",
                    "progress": 100,
                    "result": result,
                }
                notify(task.draft_id)
                logger.info("video_worker: completed %s for draft %s", task.task_type, task.draft_id)
                await _send_notifications(task.draft_id, task.task_type, "completed")

            except Exception as exc:
                error_msg = str(exc)[:500]
                await fail_task(task.task_id, error=error_msg)
                live_status[task.draft_id] = {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": "failed",
                    "step": "error",
                    "progress": 0,
                    "error": error_msg,
                }
                notify(task.draft_id)
                logger.error("video_worker: %s failed for draft %s: %s", task.task_type, task.draft_id, exc)
                await _send_notifications(task.draft_id, task.task_type, "failed")
                await _notify_admin_error(task, error_msg)

        except Exception:
            logger.exception("video_worker: unexpected error in loop")
            await asyncio.sleep(5)


async def _set_progress(task_id: str, draft_id: str, step: str, progress: int) -> None:
    """Update progress in both DB and live status."""
    await update_task_progress(task_id, step=step, progress=progress)
    if draft_id in live_status:
        live_status[draft_id]["step"] = step
        live_status[draft_id]["progress"] = progress
    notify(draft_id)


async def _execute_clean(task) -> dict:
    """Execute a video cleaning task as a subprocess.

    Runs video_processor CLI as a separate process to isolate memory usage.
    This prevents Whisper/ffmpeg from OOM-killing the gunicorn worker.
    """
    import json as _json
    import sys
    from bot.services.reels_video import VIDEO_DIR

    draft_id = task.draft_id
    task_id = task.task_id
    config = task.config or {}

    await _set_progress(task_id, draft_id, "preparing", 5)

    from bot.services.drafts_store import get_draft, update_draft
    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError("Draft not found")

    video_filename = str(draft.payload.get("video_filename") or "").strip()
    if not video_filename:
        raise ValueError("No video uploaded")

    video_path = VIDEO_DIR / draft_id / video_filename
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    output_dir = VIDEO_DIR / draft_id

    use_whisper = config.get("use_whisper", False)
    min_pause = config.get("min_pause_duration", 0.4)
    silence_db = config.get("silence_threshold_db", -35.0)

    if use_whisper:
        await _set_progress(task_id, draft_id, "transcribing", 20)
    else:
        await _set_progress(task_id, draft_id, "detecting_silence", 20)

    # Build CLI command — runs as separate process (isolated memory)
    cmd = [
        sys.executable, "-m", "bot.services.video_processor.cli",
        "--input", str(video_path),
        "--output", str(output_dir),
        "--mode", "single",
        "--min-pause", str(min_pause),
        "--silence-threshold", str(silence_db),
        "--json-output",
    ]
    if use_whisper:
        cmd += ["--whisper", "--whisper-model", "tiny"]
    else:
        cmd += ["--no-whisper"]

    logger.info("video_worker: running subprocess: %s", " ".join(cmd[:6]))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await _set_progress(task_id, draft_id, "processing", 40)

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err_text = stderr.decode("utf-8", errors="replace")
        # Log full stderr for debugging
        logger.error("video_processor stderr (rc=%d):\n%s", proc.returncode, err_text[-2000:])
        if proc.returncode == -9:
            raise RuntimeError(f"Процесс убит системой (нехватка ресурсов). Код: {proc.returncode}")
        # Take last meaningful lines for error message
        err_lines = [l for l in err_text.strip().splitlines() if l.strip() and "INFO" not in l]
        short_err = "\n".join(err_lines[-5:]) if err_lines else err_text[-300:]
        raise RuntimeError(f"video_processor rc={proc.returncode}: {short_err}")

    await _set_progress(task_id, draft_id, "assembling", 85)

    # Parse JSON output from CLI
    try:
        result_data = _json.loads(stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        # Fallback: scan output dir for cleaned file
        result_data = {}

    # Find output file
    cleaned_filename = ""
    output_files = result_data.get("output_files", [])
    if output_files:
        from pathlib import Path as _Path
        cleaned_filename = _Path(output_files[0]).name
    else:
        # Scan directory for new files
        from pathlib import Path as _Path
        existing_before = {video_path.name}
        for f in output_dir.iterdir():
            if f.suffix in (".mp4", ".mkv", ".mov") and f.name not in existing_before:
                cleaned_filename = f.name
                break

    # Save results to draft
    payload = dict(draft.payload)
    payload["cleaned_video_path"] = cleaned_filename
    payload["cleaning_status"] = "completed"
    cleaning_result = {
        "input_duration": result_data.get("total_input_duration", 0),
        "output_duration": result_data.get("total_output_duration", 0),
        "removed_duration": result_data.get("removed_duration", 0),
        "clip_count": result_data.get("clip_count", 0),
    }
    payload["cleaning_result"] = cleaning_result
    payload["keep_intervals"] = result_data.get("keep_intervals", [])
    payload["split_clips"] = []
    payload["split_status"] = ""
    await update_draft(draft_id, payload=payload)

    await _set_progress(task_id, draft_id, "done", 100)
    return cleaning_result


async def _execute_compose(task) -> dict:
    """Execute a video composition task."""
    from bot.services.video_pipeline import compose_reel

    draft_id = task.draft_id
    task_id = task.task_id
    config = task.config or {}

    await _set_progress(task_id, draft_id, "preparing", 10)
    await _set_progress(task_id, draft_id, "rendering", 30)

    result = await compose_reel(
        draft_id,
        renderer=config.get("renderer", "ffmpeg"),
        template=config.get("template", "aroma"),
        text_animation=config.get("text_animation", "fade"),
    )

    await _set_progress(task_id, draft_id, "done", 100)
    return result if isinstance(result, dict) else {"video_ready": True}


async def _execute_grade(task) -> dict:
    """Execute a video color grading task via FFmpeg subprocess."""
    from bot.services.reels_video import VIDEO_DIR
    from bot.services.drafts_store import get_draft, update_draft
    from pathlib import Path as _Path

    draft_id = task.draft_id
    task_id = task.task_id
    config = task.config or {}

    await _set_progress(task_id, draft_id, "grading", 20)

    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError("Draft not found")

    video_filename = config.get("video_filename") or ""
    if not video_filename:
        raise ValueError("No video filename in task config")

    video_path = VIDEO_DIR / draft_id / video_filename
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    vf_string = config.get("vf_string", "")
    if not vf_string:
        raise ValueError("No vf_string in task config")

    # Output file
    stem = _Path(video_filename).stem
    graded_filename = f"{stem}_graded.mp4"
    output_path = VIDEO_DIR / draft_id / graded_filename

    await _set_progress(task_id, draft_id, "encoding", 50)

    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", vf_string,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac",
        "-y", str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg grading failed (rc={proc.returncode}): {stderr.decode('utf-8', errors='replace')[:300]}")

    await _set_progress(task_id, draft_id, "saving", 90)

    # Update draft payload
    payload = dict(draft.payload)
    payload["graded_video_path"] = graded_filename
    payload["grade_vf_string"] = vf_string
    await update_draft(draft_id, payload=payload)

    await _set_progress(task_id, draft_id, "done", 100)
    return {"graded_video_path": graded_filename, "vf_string": vf_string}


async def _execute_montage(task) -> dict:
    """Execute auto-montage pipeline."""
    from bot.services.video_montage.config import MontageConfig
    from bot.services.video_montage.engine import run_montage
    from bot.services.reels_video import VIDEO_DIR
    from bot.services.drafts_store import get_draft, update_draft

    draft_id = task.draft_id
    task_id = task.task_id
    config_data = task.config or {}

    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError("Draft not found")

    payload = dict(draft.payload)
    video_filename = payload.get("cleaned_video_path") or payload.get("video_filename") or ""
    if not video_filename:
        raise ValueError("No video to montage")

    video_path = VIDEO_DIR / draft_id / video_filename
    output_path = VIDEO_DIR / draft_id / f"{Path(video_filename).stem}_montage.mp4"

    # Build montage config
    montage_config = MontageConfig(
        input_video=str(video_path),
        draft_id=draft_id,
        keep_intervals=payload.get("keep_intervals", []),
        template=config_data.get("template", "expert"),
        transitions_enabled=config_data.get("transitions_enabled", True),
        transition_type=config_data.get("transition_type", "fade"),
        subtitles_enabled=config_data.get("subtitles_enabled", True),
        subtitle_style=config_data.get("subtitle_style", "bottom_bar"),
        music_enabled=config_data.get("music_enabled", False),
        music_track=config_data.get("music_track", ""),
        music_volume=config_data.get("music_volume", 0.15),
        broll_enabled=config_data.get("broll_enabled", False),
        broll_frames=config_data.get("broll_frames", []),
        beat_sync_enabled=config_data.get("beat_sync_enabled", False),
        color_grade_enabled=config_data.get("color_grade_enabled", False),
        color_grade_vf=config_data.get("color_grade_vf", payload.get("grade_vf_string", "")),
        output_path=str(output_path),
    )
    montage_config.apply_template()

    # Get script text for subtitles
    script_text = payload.get("scenario") or payload.get("script") or ""
    storyboard = payload.get("storyboard") or []
    if not script_text and storyboard:
        script_text = " ".join(
            f.get("voiceover", "") or f.get("text", "") for f in storyboard if isinstance(f, dict)
        )

    # Progress callback
    async def _progress(step, pct):
        await _set_progress(task_id, draft_id, step, pct)

    result = await run_montage(
        montage_config,
        script_text=script_text,
        progress_callback=_progress,
    )

    if not result.success:
        raise RuntimeError(f"Montage failed: {result.error}")

    # Update draft
    payload["montage_video_path"] = Path(result.output_file).name
    payload["montage_features"] = result.features_applied
    payload["montage_duration"] = result.duration
    await update_draft(draft_id, payload=payload)

    return {
        "montage_video_path": Path(result.output_file).name,
        "features_applied": result.features_applied,
        "duration": result.duration,
    }
