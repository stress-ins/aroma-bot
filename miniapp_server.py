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
    from bot.services.brand_settings_store import preload_brand_settings
    from bot.services.drafts_store import list_recent_drafts
    from bot.services.carousel_assets import populate_carousel_slide_assets
    from bot.services.reels_assets import populate_reels_frame_assets
    from miniapp.api.generation import complete_carousel_generation, complete_reels_generation

    await preload_brand_settings()
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
    if recovery_lock is not None:
        try:
            fcntl.flock(recovery_lock.fileno(), fcntl.LOCK_UN)
        finally:
            recovery_lock.close()


app = FastAPI(lifespan=_lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="miniapp-static")


@app.middleware("http")
async def _no_cache_js_modules(request, call_next):
    """Force revalidation of ES module files that lack their own version hash."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") and (path.endswith(".js") or path.endswith(".css")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


def _setup_mounts_and_routers():
    """Register asset mounts and API routers (lazy imports for faster module load)."""
    from bot.services.reels_assets import ASSETS_DIR
    from bot.services.carousel_assets import CAROUSEL_ASSETS_DIR
    from miniapp.api.routers import (
        blend_constructor, carousel, create, drafts, keywords, mentions,
        misc, plans, publish, recommendations, references, reels, social,
        social_trends, teams, thread_monitor, threads_series, tokens, trends, user,
    )

    app.mount("/generated/reels_assets", StaticFiles(directory=ASSETS_DIR), name="reels-generated-assets")
    app.mount("/generated/carousel_assets", StaticFiles(directory=CAROUSEL_ASSETS_DIR), name="carousel-generated-assets")

    REFERENCE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/reference-images", StaticFiles(directory=REFERENCE_IMAGES_DIR), name="reference-images")

    SOUNDS_DIR = BASE_DIR / "assets" / "sounds"
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/sounds", StaticFiles(directory=SOUNDS_DIR), name="sounds")

    for _router in (
        blend_constructor.router, drafts.router, carousel.router, reels.router,
        plans.router, recommendations.router, references.router, create.router,
        keywords.router, misc.router, publish.router, social.router, social_trends.router,
        teams.router, thread_monitor.router, threads_series.router, trends.router, mentions.router,
        tokens.router, user.router,
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
