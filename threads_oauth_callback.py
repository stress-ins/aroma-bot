from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from bot.services.social_oauth import (
    OAuthExchangeError,
    OAuthTokenBundle,
    OAuthStateError,
    bundle_env_updates,
    exchange_instagram_code,
    exchange_threads_code,
    notify_telegram_chat,
    parse_oauth_state,
    update_env_file,
)
from config import settings


app = FastAPI()
logger = logging.getLogger(__name__)
ENV_FILE = Path(os.getenv("AROMA_ENV_FILE", Path(__file__).resolve().parent / ".env"))
THREADS_REDIRECT_URI = "https://oauth.aromara.ru/threads/callback"
INSTAGRAM_REDIRECT_URI = "https://oauth.aromara.ru/instagram/callback"


@app.get("/")
async def root():
    return {"ok": True, "service": "threads-oauth-callback"}


@app.get("/threads/callback")
async def threads_callback(request: Request):
    return await _complete_oauth("threads", request)


@app.get("/instagram/callback")
async def instagram_callback(request: Request):
    return await _complete_oauth("instagram", request)


@app.get("/threads/deauthorize")
async def threads_deauthorize(request: Request):
    return JSONResponse(
        {
            "ok": True,
            "service": "threads-oauth-callback",
            "event": "deauthorize",
            "query": dict(request.query_params),
        }
    )


@app.post("/threads/delete")
async def threads_delete(request: Request):
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    confirmation_code = str(payload.get("confirmation_code", "threads-delete-request")).strip() or "threads-delete-request"
    return JSONResponse(
        {
            "url": "https://oauth.aromara.ru/threads/delete/status",
            "confirmation_code": confirmation_code,
        }
    )


@app.get("/threads/delete/status")
async def threads_delete_status():
    return JSONResponse({"ok": True, "status": "received"})


@app.get("/healthz")
async def healthz():
    return JSONResponse({"ok": True})


def _render_oauth_callback_html(service: str, request: Request) -> HTMLResponse:
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error", "")
    if error:
        return HTMLResponse(f"<h1>{service} OAuth error</h1><pre>{error}</pre>", status_code=400)
    if not code:
        return HTMLResponse("<h1>No code provided</h1>", status_code=400)

    html = (
        f"<h1>{service} OAuth code received</h1>"
        f"<p>State: <code>{state}</code></p>"
        f"<p>Code:</p><pre style=\"white-space:pre-wrap;overflow-wrap:anywhere\">{code}</pre>"
        "<p>Скопируй этот code и вернись в чат.</p>"
    )
    return HTMLResponse(html)


async def _complete_oauth(service: str, request: Request) -> HTMLResponse:
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error", "")
    if error:
        return HTMLResponse(f"<h1>{service.title()} OAuth error</h1><pre>{error}</pre>", status_code=400)
    if not code:
        return HTMLResponse("<h1>No code provided</h1>", status_code=400)

    try:
        state_payload = parse_oauth_state(state=state, secret=settings.telegram_bot_token)
    except OAuthStateError as exc:
        return HTMLResponse(f"<h1>Invalid OAuth state</h1><pre>{exc}</pre>", status_code=400)

    if state_payload.service != service:
        return HTMLResponse("<h1>OAuth state/service mismatch</h1>", status_code=400)

    try:
        bundle = _exchange_bundle(service, code)
        update_env_file(ENV_FILE, bundle_env_updates(bundle))
        _restart_aroma_bot()
        _notify_success(state_payload.chat_id, bundle)
    except OAuthExchangeError as exc:
        _notify_failure(state_payload.chat_id, service, str(exc))
        return HTMLResponse(f"<h1>{service.title()} OAuth exchange failed</h1><pre>{exc}</pre>", status_code=500)
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected OAuth callback failure for %s", service)
        _notify_failure(state_payload.chat_id, service, str(exc))
        return HTMLResponse(f"<h1>{service.title()} OAuth failed</h1><pre>{exc}</pre>", status_code=500)

    html = (
        f"<h1>{service.title()} connected</h1>"
        "<p>Токен сохранён на сервере.</p>"
        "<p>Бот перезапущен и пришлёт подтверждение в Telegram.</p>"
    )
    return HTMLResponse(html)


def _exchange_bundle(service: str, code: str) -> OAuthTokenBundle:
    if service == "threads":
        return exchange_threads_code(
            code=code,
            client_id=settings.threads_app_id,
            client_secret=settings.threads_app_secret,
            redirect_uri=THREADS_REDIRECT_URI,
        )
    if service == "instagram":
        return exchange_instagram_code(
            code=code,
            client_id=settings.instagram_app_id,
            client_secret=settings.instagram_app_secret,
            redirect_uri=INSTAGRAM_REDIRECT_URI,
        )
    raise OAuthExchangeError(f"Unsupported service: {service}")


def _notify_success(chat_id: str, bundle: OAuthTokenBundle) -> None:
    if bundle.service == "threads":
        text = (
            "✅ Threads подключён.\n"
            f"Аккаунт: @{bundle.username or 'unknown'}\n"
            f"User ID: {bundle.user_id}"
        )
    else:
        text = (
            "✅ Instagram подключён.\n"
            f"User ID: {bundle.user_id}"
            + (f"\nАккаунт: @{bundle.username}" if bundle.username else "")
        )
    _notify(chat_id, text)


def _notify_failure(chat_id: str, service: str, error_text: str) -> None:
    _notify(chat_id, f"❌ Не удалось подключить {service.title()}.\n{error_text[:300]}")


def _notify(chat_id: str, text: str) -> None:
    try:
        notify_telegram_chat(bot_token=settings.telegram_bot_token, chat_id=chat_id, text=text)
    except Exception:
        logger.exception("Failed to notify Telegram chat %s", chat_id)


def _restart_aroma_bot() -> None:
    try:
        subprocess.run(["systemctl", "restart", "aroma-bot"], check=False, capture_output=True, text=True)
    except Exception:
        logger.exception("Failed to restart aroma-bot after OAuth callback")
