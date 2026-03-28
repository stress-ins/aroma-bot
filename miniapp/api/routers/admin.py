"""Admin dashboard API — system stats, video queue, LLM usage."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from miniapp.api.auth import _telegram_user_id_from_init_data, _verify_init_data
from fastapi import Header

logger = logging.getLogger(__name__)
router = APIRouter()

# Admin user IDs (from config)
def _get_admin_ids() -> set[int]:
    from config import settings
    admin_id = getattr(settings, "admin_telegram_chat_id", "")
    if admin_id:
        try:
            return {int(admin_id)}
        except (ValueError, TypeError):
            logger.warning("_get_admin_ids: int failed", exc_info=True)
            pass
    return set()


def _require_admin(x_telegram_init_data: str | None = Header(default=None)) -> int:
    """Require admin access — returns telegram_id or raises 403."""
    if os.getenv("AROMA_BYPASS_AUTH") == "1" and os.getenv("AROMA_ENV", "production") in ("test", "dev"):
        return 12345
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data)
    if not user_id:
        raise HTTPException(status_code=403, detail="forbidden")
    admin_ids = _get_admin_ids()
    if admin_ids and user_id not in admin_ids:
        raise HTTPException(status_code=403, detail="not_admin")
    return user_id


def _resolve_user(x_telegram_init_data: str | None = Header(default=None)) -> tuple[int, bool]:
    """Returns (telegram_id, is_admin)."""
    import os
    if os.getenv("AROMA_BYPASS_AUTH") == "1" and os.getenv("AROMA_ENV", "production") in ("test", "dev"):
        return 12345, True
    if not x_telegram_init_data or not _verify_init_data(x_telegram_init_data):
        raise HTTPException(status_code=403, detail="forbidden")
    user_id = _telegram_user_id_from_init_data(x_telegram_init_data)
    if not user_id:
        raise HTTPException(status_code=403, detail="forbidden")
    admin_ids = _get_admin_ids()
    return user_id, (user_id in admin_ids if admin_ids else False)


@router.get("/api/admin/dashboard")
async def admin_dashboard(user_info: tuple = Depends(_resolve_user)):
    """System dashboard — video queue, LLM usage, memory stats."""
    user_id, is_admin = user_info
    from db.session import AsyncSessionLocal
    from db.models import VideoTaskModel
    from sqlalchemy import func, select

    # ── Video task queue stats ──
    async with AsyncSessionLocal() as session:
        # Counts by status
        q = (
            select(
                VideoTaskModel.status,
                VideoTaskModel.task_type,
                func.count(VideoTaskModel.id),
            )
            .group_by(VideoTaskModel.status, VideoTaskModel.task_type)
        )
        rows = (await session.execute(q)).all()

        queue_stats: dict[str, dict[str, int]] = {}
        for status, task_type, count in rows:
            queue_stats.setdefault(status, {})[task_type] = count

        # Recent tasks (last 20)
        recent_q = (
            select(VideoTaskModel)
            .order_by(VideoTaskModel.created_at.desc())
            .limit(20)
        )
        recent_rows = (await session.execute(recent_q)).scalars().all()
        recent_tasks = [
            {
                "task_id": t.task_id[:8],
                "draft_id": t.draft_id[:8],
                "type": t.task_type,
                "status": t.status,
                "step": t.step,
                "progress": t.progress,
                "error": (t.error or "")[:100],
                "duration_sec": round((t.finished_at - t.started_at).total_seconds(), 1) if t.finished_at and t.started_at else None,
                "created": t.created_at.isoformat() if t.created_at else None,
            }
            for t in recent_rows
        ]

        # Active (pending + running)
        active_q = (
            select(func.count(VideoTaskModel.id))
            .where(VideoTaskModel.status.in_(["pending", "running"]))
        )
        active_count = (await session.execute(active_q)).scalar() or 0

    # ── LLM cache stats (today) ──
    llm_stats = {}
    try:
        from db.models import LlmCacheModel
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        async with AsyncSessionLocal() as session:
            total_today = (await session.execute(
                select(func.count(LlmCacheModel.id))
                .where(LlmCacheModel.created_at >= today_start)
            )).scalar() or 0
            total_all = (await session.execute(
                select(func.count(LlmCacheModel.id))
            )).scalar() or 0
            llm_stats = {"today": total_today, "total": total_all}
    except Exception:
        llm_stats = {"today": 0, "total": 0}

    # ── System memory ──
    memory = {}
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
            total_mb = meminfo.get("MemTotal", 0) // 1024
            avail_mb = meminfo.get("MemAvailable", 0) // 1024
            swap_total_mb = meminfo.get("SwapTotal", 0) // 1024
            swap_free_mb = meminfo.get("SwapFree", 0) // 1024
            memory = {
                "ram_total_mb": total_mb,
                "ram_used_mb": total_mb - avail_mb,
                "ram_available_mb": avail_mb,
                "ram_percent": round((total_mb - avail_mb) / total_mb * 100, 1) if total_mb else 0,
                "swap_total_mb": swap_total_mb,
                "swap_used_mb": swap_total_mb - swap_free_mb,
                "swap_percent": round((swap_total_mb - swap_free_mb) / swap_total_mb * 100, 1) if swap_total_mb else 0,
            }
    except Exception:
        memory = {"ram_total_mb": 0, "ram_used_mb": 0, "ram_percent": 0}

    # ── Worker status ──
    from bot.services import video_task_worker
    worker_alive = video_task_worker._worker_task is not None and not video_task_worker._worker_task.done()
    live_tasks = {
        k: {"type": v.get("task_type"), "status": v.get("status"), "step": v.get("step"), "progress": v.get("progress")}
        for k, v in video_task_worker.live_status.items()
    }

    # ── Canva worker status ──
    from bot.services import canva_task_worker
    canva_worker_alive = canva_task_worker._worker_task is not None and not canva_task_worker._worker_task.done()
    canva_live_tasks = {
        k: {
            "type": v.get("task_type"),
            "status": v.get("status"),
            "step": v.get("step"),
            "error": (v.get("error") or "")[:200],
            "result": v.get("result"),
        }
        for k, v in canva_task_worker.live_status.items()
    }

    # ── Disk usage ──
    disk = {}
    try:
        import shutil
        usage = shutil.disk_usage("/opt/aroma/data")
        disk = {
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
            "percent": round(usage.used / usage.total * 100, 1),
        }
    except Exception:
        logger.warning("admin: suppressed exception", exc_info=True)
        pass

    result = {
        "is_admin": is_admin,
        "video_queue": {
            "active": active_count,
            "by_status": queue_stats,
            "recent": recent_tasks,
            "live": live_tasks,
        },
    }

    # Admin-only details
    if is_admin:
        result["worker"] = {"alive": worker_alive}
        result["canva_worker"] = {"alive": canva_worker_alive, "live": canva_live_tasks}
        result["llm"] = llm_stats
        result["memory"] = memory
        result["disk"] = disk

    return result


@router.post("/api/admin/reset-stuck-tasks")
async def reset_stuck_tasks(_: int = Depends(_require_admin)):
    """Reset any stuck running tasks back to pending."""
    from bot.services.video_task_store import recover_interrupted_tasks
    count = await recover_interrupted_tasks()
    return {"reset": count}


@router.post("/api/admin/restart-worker")
async def restart_worker(_: int = Depends(_require_admin)):
    """Restart the video task worker."""
    from bot.services.video_task_worker import start_worker
    await start_worker()
    return {"status": "restarted"}
