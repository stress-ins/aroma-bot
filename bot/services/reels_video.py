"""Video tech-check and publish helpers for reels_v2 drafts."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.services.drafts_store import get_draft, update_draft
from bot.services.reels_assets import ASSETS_DIR

logger = logging.getLogger(__name__)

VIDEO_DIR = Path(os.getenv("AROMA_REELS_VIDEO_DIR", Path(__file__).parent.parent.parent / "data" / "reels_video"))
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# Limits
MAX_DURATION_SECONDS = 90
MAX_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
MIN_WIDTH = 1080
MIN_HEIGHT = 1920
TARGET_RATIO = 9 / 16


def _ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def _run_ffprobe(video_path: Path) -> dict[str, Any] | None:
    """Run ffprobe on a video file, return parsed JSON or None."""
    if not _ffprobe_available():
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-show_format",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("ffprobe failed for %s: %s", video_path, result.stderr[:200])
            return None
        return json.loads(result.stdout)
    except Exception as exc:
        logger.warning("ffprobe error for %s: %s", video_path, exc)
        return None


def _tech_check_ffprobe(video_path: Path) -> dict[str, Any]:
    """Run tech check via ffprobe. Returns check result dict."""
    issues: list[str] = []
    info: dict[str, Any] = {}

    file_size = video_path.stat().st_size
    if file_size > MAX_SIZE_BYTES:
        issues.append(f"Файл слишком большой: {file_size / 1e9:.1f} ГБ (лимит 2 ГБ)")
    info["file_size_mb"] = round(file_size / 1e6, 1)

    probe = _run_ffprobe(video_path)
    if probe is None:
        return {
            "passed": False,
            "issues": ["ffprobe недоступен — проверка не выполнена"],
            "info": info,
        }

    streams = probe.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = probe.get("format", {})

    # Duration
    duration = float(fmt.get("duration") or (video_stream or {}).get("duration") or 0)
    info["duration_seconds"] = round(duration, 1)
    if duration > MAX_DURATION_SECONDS:
        issues.append(f"Видео слишком длинное: {duration:.0f} сек (лимит {MAX_DURATION_SECONDS} сек)")

    # Resolution
    if video_stream:
        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)
        info["width"] = width
        info["height"] = height
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            issues.append(f"Разрешение {width}×{height} ниже минимального {MIN_WIDTH}×{MIN_HEIGHT}")
        # Aspect ratio
        if width > 0 and height > 0:
            ratio = width / height
            if abs(ratio - TARGET_RATIO) > 0.05:
                issues.append(f"Соотношение сторон {width}:{height} не соответствует 9:16")

    # Audio
    if not audio_stream:
        issues.append("Аудиодорожка отсутствует")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "info": info,
    }


def _tech_check_basic(video_path: Path) -> dict[str, Any]:
    """Minimal check when ffprobe is unavailable — only file size."""
    issues: list[str] = []
    file_size = video_path.stat().st_size
    if file_size > MAX_SIZE_BYTES:
        issues.append(f"Файл слишком большой: {file_size / 1e9:.1f} ГБ (лимит 2 ГБ)")
    if file_size == 0:
        issues.append("Файл пустой")
    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "info": {"file_size_mb": round(file_size / 1e6, 1)},
        "note": "ffprobe не установлен — выполнена только базовая проверка размера",
    }


def _video_path_for_draft(draft_id: str, payload: dict[str, Any]) -> Path | None:
    """Resolve local video file path for a reels_v2 draft."""
    video_filename = str(payload.get("video_filename") or "").strip()
    if video_filename:
        path = VIDEO_DIR / draft_id / video_filename
        if path.exists():
            return path
    return None


async def check_video_tech(draft_id: str) -> dict[str, Any] | None:
    """Run tech check on uploaded video for a reels_v2 draft."""
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None

    video_path = _video_path_for_draft(draft_id, draft.payload)
    if video_path is None:
        return {
            "draft_id": draft_id,
            "video_status": str(draft.payload.get("video_status") or "none"),
            "tech_check": None,
            "message": "Видео ещё не загружено",
        }

    if _ffprobe_available():
        tech_check = _tech_check_ffprobe(video_path)
    else:
        tech_check = _tech_check_basic(video_path)

    # Persist result
    payload = dict(draft.payload)
    payload["tech_check"] = tech_check
    new_status = "passed" if tech_check["passed"] else "failed"
    payload["video_status"] = new_status
    await update_draft(draft_id, payload=payload, status=new_status if new_status == "passed" else "video_uploaded")

    return {
        "draft_id": draft_id,
        "video_status": new_status,
        "tech_check": tech_check,
    }


async def save_uploaded_video(draft_id: str, video_bytes: bytes, filename: str) -> dict[str, Any]:
    """Save uploaded video bytes and update draft payload."""
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        raise ValueError(f"Draft {draft_id} not found or not reels_v2")

    video_dir = VIDEO_DIR / draft_id
    video_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"video_{draft_id[:8]}_{filename[-40:]}"
    video_path = video_dir / safe_filename
    video_path.write_bytes(video_bytes)

    payload = dict(draft.payload)
    payload["video_filename"] = safe_filename
    payload["video_status"] = "uploaded"
    payload["video_uploaded_at"] = datetime.now(timezone.utc).isoformat()
    await update_draft(draft_id, payload=payload, status="video_uploaded")

    return {"video_filename": safe_filename, "video_status": "uploaded"}


async def publish_reels_video(
    draft_id: str,
    *,
    platforms: list[str],
    date: str = "",
    time: str = "",
    youtube_title: str = "",
    youtube_privacy: str = "public",
) -> dict[str, Any] | None:
    """Publish a reels_v2 draft video via direct platform APIs."""
    draft = await get_draft(draft_id)
    if not draft or draft.kind != "reels_v2":
        return None

    from config import settings

    video_path = _video_path_for_draft(draft_id, draft.payload)
    caption = str(draft.payload.get("caption") or "")

    # Build public video URL for platforms that need it (Instagram, Threads)
    video_public_url = ""
    if video_path and video_path.exists():
        base = getattr(settings, "assets_base_url", "") or ""
        video_filename = draft.payload.get("video_filename", "")
        if base and video_filename:
            video_public_url = f"{base}/generated/reels_video/{draft_id}/{video_filename}"

    results: list[dict[str, Any]] = []

    for platform in platforms:
        entry: dict[str, Any] = {"platform": platform, "published_at": datetime.now(timezone.utc).isoformat()}
        try:
            if platform == "instagram":
                if not video_public_url:
                    raise RuntimeError("Нет публичного URL для видео — проверьте assets_base_url")
                from bot.services.meta_publisher import publish_to_instagram_reels
                result = await publish_to_instagram_reels(caption, video_public_url)
                entry["status"] = "success"
                entry["external_id"] = str(result.get("id", ""))

            elif platform == "threads":
                if not video_public_url:
                    raise RuntimeError("Нет публичного URL для видео — проверьте assets_base_url")
                from bot.services.meta_publisher import publish_to_threads
                result = await publish_to_threads(text=caption, video_url=video_public_url)
                entry["status"] = "success"
                entry["external_id"] = str(result.get("id", ""))

            elif platform == "youtube":
                if not video_path or not video_path.exists():
                    raise RuntimeError("Видеофайл не найден")
                from bot.services.youtube_publisher import publish_to_youtube
                yt_title = youtube_title or draft.topic or caption[:100]
                result = await publish_to_youtube(
                    video_path=video_path,
                    title=yt_title,
                    description=caption,
                    privacy=youtube_privacy,
                )
                entry["status"] = "success"
                entry["external_id"] = str(result.get("id", ""))
                entry["url"] = str(result.get("url", ""))

            else:
                entry["status"] = "failed"
                entry["error"] = f"Неизвестная платформа: {platform}"

        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)[:300]
            logger.error("Failed to publish reels %s to %s: %s", draft_id, platform, exc)

        results.append(entry)

    payload = dict(draft.payload)
    existing = list(payload.get("publish_status") or [])
    # Merge: update by platform
    existing_by_platform = {e["platform"]: e for e in existing if isinstance(e, dict)}
    for r in results:
        existing_by_platform[r["platform"]] = r
    payload["publish_status"] = list(existing_by_platform.values())

    all_ok = all(r.get("status") == "success" for r in results)
    new_draft_status = "published" if all_ok and results else "publishing"
    await update_draft(draft_id, payload=payload, status=new_draft_status)

    return {
        "draft_id": draft_id,
        "publish_status": payload["publish_status"],
    }
