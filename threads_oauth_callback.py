from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from bot.services.mentions_store import upsert_token
from bot.services.social_oauth import (
    INSTAGRAM_REDIRECT_URI,
    THREADS_REDIRECT_URI,
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


def _success_page(service: str, username: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{service} connected</title>
<style>
  body {{ font-family: -apple-system, sans-serif; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; margin: 0; background: #f5f5f5; }}
  .card {{ background: white; border-radius: 12px; padding: 40px; text-align: center;
           max-width: 400px; box-shadow: 0 2px 20px rgba(0,0,0,.08); }}
  h1 {{ font-size: 22px; margin: 0 0 8px; color: #1a1a1a; }}
  p {{ color: #666; margin: 8px 0 0; }}
</style></head>
<body><div class="card">
  <div style="font-size:48px;margin-bottom:12px">&#x2705;</div>
  <h1>{service} connected</h1>
  <p>Account <strong>@{username}</strong> linked successfully.<br>
  You can close this window and return to the bot.</p>
</div></body></html>""")


def _error_page(message: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Error</title>
<style>
  body {{ font-family: -apple-system, sans-serif; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; margin: 0; background: #f5f5f5; }}
  .card {{ background: white; border-radius: 12px; padding: 40px; text-align: center;
           max-width: 400px; box-shadow: 0 2px 20px rgba(0,0,0,.08); }}
  h1 {{ font-size: 22px; margin: 0 0 8px; color: #c0392b; }}
  p {{ color: #666; margin: 8px 0 0; font-size: 14px; }}
</style></head>
<body><div class="card">
  <div style="font-size:48px;margin-bottom:12px">&#x274C;</div>
  <h1>Connection failed</h1>
  <p>{message}</p>
</div></body></html>""", status_code=400)


async def _store_token_in_db(bundle: OAuthTokenBundle) -> None:
    """Persist OAuth token and user_id in PlatformTokenModel."""
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=bundle.expires_in)
        if bundle.expires_in else None
    )
    await upsert_token(bundle.service, bundle.access_token, expires_at)
    await upsert_token(f"{bundle.service}_user_id", bundle.user_id, None)
    logger.info("Stored %s token in DB for user %s (id=%s)", bundle.service, bundle.username, bundle.user_id)


async def _complete_oauth(service: str, request: Request) -> HTMLResponse:
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error", "")
    if error:
        desc = request.query_params.get("error_description", error)
        return _error_page(f"Meta returned an error: {desc}")
    if not code:
        return _error_page("Authorization code is missing.")

    chat_id: str | None = None
    logger.info(
        "OAuth callback: service=%s, state[:30]=%s, secret[:5]=%s",
        service,
        state[:30] if state else "<empty>",
        settings.telegram_bot_token[:5],
    )
    try:
        state_payload = parse_oauth_state(state=state, secret=settings.telegram_bot_token)
        chat_id = state_payload.chat_id
        if state_payload.service != service:
            logger.warning("OAuth state/service mismatch: expected %s, got %s", service, state_payload.service)
    except OAuthStateError as exc:
        logger.warning("OAuth state validation failed (non-fatal): %s", exc)

    try:
        bundle = _exchange_bundle(service, code)
        update_env_file(ENV_FILE, bundle_env_updates(bundle))
        await _store_token_in_db(bundle)
        _restart_aroma_bot()
        if chat_id:
            _notify_success(chat_id, bundle)
    except OAuthExchangeError as exc:
        if chat_id:
            _notify_failure(chat_id, service, str(exc))
        return _error_page(f"Token exchange failed: {exc}")
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected OAuth callback failure for %s", service)
        if chat_id:
            _notify_failure(chat_id, service, str(exc))
        return _error_page(f"Unexpected error: {exc}")

    return _success_page(service.title(), bundle.username or "unknown")


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
