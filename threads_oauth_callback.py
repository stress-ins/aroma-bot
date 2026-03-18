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
    extract_state_payload_unsafe,
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


def _styled_page(*, success: bool, title: str, subtitle: str | None = None, detail: str | None = None) -> str:
    icon_color = "#4ade80" if success else "#f87171"
    icon_svg = (
        '<circle cx="32" cy="32" r="30" stroke="{c}" stroke-width="3" fill="none"/>'
        '<path d="M20 33l8 8 16-16" stroke="{c}" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    ).format(c=icon_color) if success else (
        '<circle cx="32" cy="32" r="30" stroke="{c}" stroke-width="3" fill="none"/>'
        '<path d="M22 22l20 20M42 22l-20 20" stroke="{c}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    ).format(c=icon_color)

    subtitle_html = f'<p style="font-size:18px;color:#c0785c;font-weight:600;margin:4px 0 0">{subtitle}</p>' if subtitle else ""
    detail_html = f'<p style="font-size:14px;color:#9ca3af;margin:8px 0 0">{detail}</p>' if detail else ""
    bot_user = settings.telegram_bot_username
    tg_link = f"https://t.me/{bot_user}" if bot_user else ""
    tg_btn = (
        f'<a href="{tg_link}" style="display:inline-block;margin-top:24px;padding:12px 32px;'
        f'background:#c0785c;color:#fff;border-radius:12px;text-decoration:none;font-weight:600;font-size:15px">'
        f'Вернуться в Telegram</a>'
    ) if tg_link else ""

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Aroma OAuth</title></head>'
        '<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;'
        'background:#1a1a2e;font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#e5e7eb">'
        '<div style="text-align:center;padding:40px 24px;max-width:380px">'
        f'<svg width="64" height="64" viewBox="0 0 64 64" style="margin-bottom:20px">{icon_svg}</svg>'
        f'<h1 style="font-size:22px;font-weight:700;margin:0;color:#fff">{title}</h1>'
        f'{subtitle_html}{detail_html}{tg_btn}'
        '</div></body></html>'
    )


async def _complete_oauth(service: str, request: Request) -> HTMLResponse:
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error", "")
    if error:
        return HTMLResponse(_styled_page(success=False, title=f"{service.title()} — ошибка", detail=error), status_code=400)
    if not code:
        return HTMLResponse(_styled_page(success=False, title="Ошибка", detail="No code provided"), status_code=400)

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
        raw = extract_state_payload_unsafe(state)
        chat_id = str(raw.get("chat_id", "")).strip() or None
        if chat_id:
            logger.info("Extracted chat_id=%s from unsigned state payload", chat_id)

    try:
        bundle = _exchange_bundle(service, code)
        update_env_file(ENV_FILE, bundle_env_updates(bundle))
        _restart_aroma_bot()
        if chat_id:
            _notify_success(chat_id, bundle)
    except OAuthExchangeError as exc:
        if chat_id:
            _notify_failure(chat_id, service, str(exc))
        return HTMLResponse(_styled_page(success=False, title=f"{service.title()} — ошибка обмена", detail=str(exc)), status_code=500)
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected OAuth callback failure for %s", service)
        if chat_id:
            _notify_failure(chat_id, service, str(exc))
        return HTMLResponse(_styled_page(success=False, title=f"{service.title()} — ошибка", detail=str(exc)), status_code=500)

    return HTMLResponse(_styled_page(
        success=True,
        title=f"{service.title()} подключён",
        subtitle=f"@{bundle.username}" if bundle.username else None,
        detail="Токен сохранён. Бот перезапущен.",
    ))


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
