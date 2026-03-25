from __future__ import annotations

import asyncio
import fcntl
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
MINIAPP_DIR = BASE_DIR / "miniapp"
STATIC_DIR = MINIAPP_DIR / "static"
REFERENCE_IMAGES_DIR = BASE_DIR / "assets" / "reference_images"
STARTUP_RECOVERY_LOCK_PATH = Path(
    os.getenv("AROMA_MINIAPP_RECOVERY_LOCK", "/tmp/aroma-miniapp-recovery.lock")
)

_ready = False


def _asset_version() -> str:
    parts: list[str] = []
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file() and path.suffix in (".css", ".js"):
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:10]


def _acquire_startup_recovery_lock():
    STARTUP_RECOVERY_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = STARTUP_RECOVERY_LOCK_PATH.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    return lock_file


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    """On startup: load brand settings and resume any interrupted generations."""
    global _ready
    _ready = False

    from bot.services.brand_settings_store import preload_brand_settings
    from bot.services.drafts_store import list_recent_drafts
    from bot.services.carousel_assets import populate_carousel_slide_assets
    from bot.services.reels_assets import populate_reels_frame_assets
    from miniapp.api.generation import complete_carousel_generation, complete_reels_generation
    from bot.services.kie_task_store import cleanup_expired

    await preload_brand_settings()
    _ready = True  # ready to serve traffic before recovery

    # Periodic cleanup of expired KIE tasks
    async def _periodic_kie_cleanup():
        while True:
            await asyncio.sleep(30 * 60)  # every 30 minutes
            try:
                count = await cleanup_expired()
                if count:
                    logger.info("kie_cleanup: expired %d stale tasks", count)
            except Exception:
                logger.debug("kie_cleanup: error", exc_info=True)

    asyncio.create_task(_periodic_kie_cleanup())

    # Start video task worker (picks up pending tasks from DB)
    from bot.services.video_task_worker import start_worker as _start_video_worker
    await _start_video_worker()

    # Start Canva task worker (background export/import)
    from bot.services.canva_task_worker import start_worker as _start_canva_worker
    await _start_canva_worker()

    recovery_lock = _acquire_startup_recovery_lock()
    try:
        if recovery_lock is not None:
            draft_records = await list_recent_drafts(limit=200)
            for draft in draft_records:
                payload = draft.payload or {}
                if not payload.get("generation_pending"):
                    continue
                if draft.kind == "carousel":
                    if payload.get("slides"):
                        asyncio.create_task(populate_carousel_slide_assets(draft.draft_id))
                    else:
                        asyncio.create_task(complete_carousel_generation(draft.draft_id, draft.topic))
                elif draft.kind == "reels":
                    if payload.get("storyboard"):
                        asyncio.create_task(populate_reels_frame_assets(draft.draft_id))
                    else:
                        asyncio.create_task(complete_reels_generation(draft.draft_id, draft.topic))
    except Exception:
        logger.exception("Startup recovery failed")
    yield
    _ready = False
    if recovery_lock is not None:
        try:
            fcntl.flock(recovery_lock.fileno(), fcntl.LOCK_UN)
        finally:
            recovery_lock.close()


app = FastAPI(lifespan=_lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="miniapp-static")


@app.middleware("http")
async def _security_headers(request, call_next):
    """Add security headers + force revalidation of JS/CSS modules."""
    response = await call_next(request)
    # Security headers (supplement nginx — defence in depth)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' https://telegram.org 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self'; frame-ancestors 'none';",
    )
    # Cache control for JS/CSS modules
    path = request.url.path
    if path.startswith("/static/") and (path.endswith(".js") or path.endswith(".css")):
        response.headers["Cache-Control"] = "no-cache"
    return response


def _setup_mounts_and_routers():
    """Register asset mounts and API routers (lazy imports for faster module load)."""
    from bot.services.reels_assets import ASSETS_DIR
    from bot.services.carousel_assets import CAROUSEL_ASSETS_DIR
    from miniapp.api.routers import (
        archive, blend_constructor, carousel, create, drafts, hashtags, keywords,
        mentions, misc, plans, publish, rag, recommendations, references, reels,
        repurpose, schedule, series, social, social_trends, stock_photos, teams,
        thread_monitor, threads_series, tokens, tone, trend_cards, trends,
        user, webhooks,
    )

    app.mount("/generated/reels_assets", StaticFiles(directory=ASSETS_DIR), name="reels-generated-assets")
    app.mount("/generated/carousel_assets", StaticFiles(directory=CAROUSEL_ASSETS_DIR), name="carousel-generated-assets")

    from bot.services.reels_video import VIDEO_DIR
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/generated/reels_video", StaticFiles(directory=VIDEO_DIR), name="reels-generated-video")

    REFERENCE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/reference-images", StaticFiles(directory=REFERENCE_IMAGES_DIR), name="reference-images")

    SOUNDS_DIR = BASE_DIR / "assets" / "sounds"
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/sounds", StaticFiles(directory=SOUNDS_DIR), name="sounds")

    from bot.services.content_assets import CONTENT_ASSETS_DIR
    CONTENT_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/generated/content_assets", StaticFiles(directory=CONTENT_ASSETS_DIR), name="content-generated-assets")

    MUSIC_DIR = Path(__file__).parent / "assets" / "music"
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/generated/music", StaticFiles(directory=MUSIC_DIR), name="music-library")

    for _router in (
        archive.router, blend_constructor.router, drafts.router, carousel.router, reels.router,
        plans.router, rag.router, recommendations.router, references.router, create.router,
        hashtags.router, keywords.router, misc.router, publish.router, repurpose.router,
        schedule.router, series.router, social.router, social_trends.router, teams.router,
        thread_monitor.router, threads_series.router, tone.router, trend_cards.router,
        trends.router, mentions.router, stock_photos.router,
        tokens.router, user.router, webhooks.router,
    ):
        app.include_router(_router)


_setup_mounts_and_routers()


_TELEGRAM_STUB_JS = (
    "window.Telegram={WebApp:{initData:'',initDataUnsafe:{user:{id:12345}},"
    "ready:function(){},expand:function(){},close:function(){},"
    "MainButton:{show:function(){},hide:function(){},setText:function(){},onClick:function(){}},"
    "BackButton:{show:function(){},hide:function(){},onClick:function(){}},"
    "themeParams:{},colorScheme:'light',isExpanded:true,"
    "setHeaderColor:function(){},setBackgroundColor:function(){},"
    "onEvent:function(){},offEvent:function(){},sendData:function(){},openLink:function(){},"
    "HapticFeedback:{impactOccurred:function(){},notificationOccurred:function(){},selectionChanged:function(){}}}};"
)


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (MINIAPP_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("__ASSET_VERSION__", _asset_version())
    if os.getenv("AROMA_BYPASS_AUTH") == "1":
        html = html.replace(
            '<script src="https://telegram.org/js/telegram-web-app.js"></script>',
            f"<script>{_TELEGRAM_STUB_JS}</script>",
        )
    return HTMLResponse(
        content=html,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    html = (MINIAPP_DIR / "privacy.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)
