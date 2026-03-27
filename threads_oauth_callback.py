from __future__ import annotations

import hashlib
import hmac
import logging
import os
import subprocess
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from bot.services.social_oauth import (
    OAuthExchangeError,
    OAuthTokenBundle,
    OAuthStateError,
    bundle_env_updates,
    exchange_canva_code,
    exchange_facebook_code,
    exchange_instagram_code,
    exchange_threads_code,
    exchange_youtube_code,
    extract_state_payload_unsafe,
    notify_telegram_chat,
    parse_oauth_state,
    update_env_file,
)
from bot.services.mentions_store import upsert_token
from config import settings


app = FastAPI()
logger = logging.getLogger(__name__)
ENV_FILE = Path(os.getenv("AROMA_ENV_FILE", Path(__file__).resolve().parent / ".env"))
THREADS_REDIRECT_URI = "https://oauth.aromara.ru/threads/callback"
INSTAGRAM_REDIRECT_URI = "https://oauth.aromara.ru/instagram/callback"
CANVA_REDIRECT_URI = "https://oauth.aromara.ru/canva/callback"
YOUTUBE_REDIRECT_URI = "https://oauth.aromara.ru/youtube/callback"
FACEBOOK_REDIRECT_URI = "https://oauth.aromara.ru/facebook/callback"


@app.get("/")
async def root():
    return {"ok": True, "service": "threads-oauth-callback"}


@app.get("/start")
async def oauth_start(url: str = "", platform: str = ""):
    """Intermediate page to bypass iOS Universal Links.

    Instagram app intercepts instagram.com URLs via Universal Links and
    can't handle /oauth/authorize.  A user-initiated click on our domain
    followed by JS location.href avoids the interception.
    """
    if not url or not url.startswith("https://"):
        return HTMLResponse("<h1>Missing url parameter</h1>", status_code=400)
    import json
    safe_url_js = json.dumps(url)
    label = "Instagram" if "instagram" in url.lower() else "Threads" if "threads" in url.lower() else platform or "платформу"
    # Simple JS redirect — works for both Instagram consent URL and Threads
    return HTMLResponse(
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Подключение</title></head>'
        '<body style="margin:0;min-height:100vh;display:flex;align-items:center;'
        'justify-content:center;background:#1a1a2e;color:#e5e7eb;'
        'font-family:-apple-system,BlinkMacSystemFont,sans-serif;text-align:center">'
        '<div style="padding:40px 24px;max-width:380px">'
        '<svg width="64" height="64" viewBox="0 0 64 64" style="margin-bottom:20px">'
        '<circle cx="32" cy="32" r="30" stroke="#c0785c" stroke-width="3" fill="none"/>'
        '<path d="M20 32l8 8 16-16" stroke="#c0785c" stroke-width="3" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'
        f'<h1 style="font-size:22px;font-weight:700;margin:0;color:#fff">Подключение {label}</h1>'
        '<p style="font-size:15px;color:#9ca3af;margin:12px 0 24px">Перенаправляю...</p>'
        f'<script>window.location.replace({safe_url_js});</script>'
        '</div></body></html>'
    )


@app.get("/threads/callback")
async def threads_callback(request: Request):
    return await _complete_oauth("threads", request)


@app.get("/instagram/callback")
async def instagram_callback(request: Request):
    return await _complete_oauth("instagram", request)


@app.get("/canva/callback")
async def canva_callback(request: Request):
    return await _complete_oauth("canva", request)


@app.get("/youtube/callback")
async def youtube_callback(request: Request):
    return await _complete_oauth("youtube", request)


@app.get("/facebook/callback")
async def facebook_callback(request: Request):
    return await _complete_oauth("facebook", request)


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


# ---------------------------------------------------------------------------
# Meta Webhooks — Instagram & Threads real-time events
# ---------------------------------------------------------------------------

def _verify_meta_signature(body: bytes, signature_header: str, app_secret: str) -> bool:
    """Validate X-Hub-Signature-256 from Meta webhook payload."""
    if not signature_header or not app_secret:
        return False
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    expected = hmac.new(
        app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature_header[len(prefix):], expected)


def _parse_meta_webhook_entries(payload: dict, platform: str) -> list[dict]:
    """Extract mention-like objects from Meta webhook entry[].changes[]."""
    items: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            # Each change has a field (e.g. "comments", "mentions") and value
            field = change.get("field", "")
            external_id = str(value.get("id") or value.get("comment_id") or value.get("media_id") or "")
            content = value.get("text") or value.get("message") or value.get("caption") or ""
            author = value.get("from", {})
            items.append({
                "platform": platform,
                "external_id": external_id,
                "type": field or "webhook",
                "author_username": author.get("username", ""),
                "author_name": author.get("name", ""),
                "content": str(content),
            })
    return items


async def _forward_to_ingest(items: list[dict]) -> None:
    """Forward parsed webhook items to local mentions ingest API."""
    if not items:
        logger.info("No items to forward from webhook")
        return
    secret = settings.n8n_webhook_secret
    if not secret:
        logger.warning("n8n_webhook_secret not set, cannot forward webhook items")
        return
    async with httpx.AsyncClient(timeout=10) as client:
        for item in items:
            try:
                resp = await client.post(
                    "http://127.0.0.1:8091/api/mentions/ingest",
                    json=item,
                    headers={"X-Webhook-Secret": secret},
                )
                if resp.status_code >= 400:
                    logger.error(
                        "Ingest API returned %s for item %s: %s",
                        resp.status_code, item.get("external_id"), resp.text,
                    )
                else:
                    logger.info("Forwarded webhook item %s → %s", item.get("external_id"), resp.status_code)
            except Exception:
                logger.exception("Failed to forward webhook item %s", item.get("external_id"))


@app.get("/webhooks/instagram")
async def instagram_webhook_verify(request: Request):
    """Instagram webhook verification (hub.mode=subscribe)."""
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")
    if mode == "subscribe" and hmac.compare_digest(token, settings.meta_webhook_verify_token):
        logger.info("Instagram webhook verified")
        return PlainTextResponse(challenge)
    logger.warning("Instagram webhook verification failed: mode=%s", mode)
    return JSONResponse({"error": "verification_failed"}, status_code=403)


@app.post("/webhooks/instagram")
async def instagram_webhook_handler(request: Request):
    """Handle Instagram real-time webhook events."""
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    if not _verify_meta_signature(body, signature, settings.instagram_app_secret):
        logger.warning("Instagram webhook: invalid signature")
        return JSONResponse({"error": "invalid_signature"}, status_code=403)
    payload = await request.json()
    logger.info("Instagram webhook payload: %s", payload)
    items = _parse_meta_webhook_entries(payload, "instagram")
    logger.info("Parsed %d items from Instagram webhook", len(items))
    await _forward_to_ingest(items)
    return JSONResponse({"status": "ok"})


@app.get("/webhooks/threads")
async def threads_webhook_verify(request: Request):
    """Threads webhook verification (hub.mode=subscribe)."""
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")
    if mode == "subscribe" and hmac.compare_digest(token, settings.meta_webhook_verify_token):
        logger.info("Threads webhook verified")
        return PlainTextResponse(challenge)
    logger.warning("Threads webhook verification failed: mode=%s", mode)
    return JSONResponse({"error": "verification_failed"}, status_code=403)


@app.post("/webhooks/threads")
async def threads_webhook_handler(request: Request):
    """Handle Threads real-time webhook events."""
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    if not _verify_meta_signature(body, signature, settings.threads_app_secret):
        logger.warning("Threads webhook: invalid signature")
        return JSONResponse({"error": "invalid_signature"}, status_code=403)
    payload = await request.json()
    logger.info("Threads webhook payload: %s", payload)
    items = _parse_meta_webhook_entries(payload, "threads")
    logger.info("Parsed %d items from Threads webhook", len(items))
    await _forward_to_ingest(items)
    return JSONResponse({"status": "ok"})


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

    # Extract code_verifier for PKCE (Canva)
    _raw_state = extract_state_payload_unsafe(state)
    code_verifier = str(_raw_state.get("code_verifier", "")).strip()

    try:
        bundle = _exchange_bundle(service, code, code_verifier=code_verifier)
        update_env_file(ENV_FILE, bundle_env_updates(bundle))
        await _save_token_to_db(service, bundle)
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


async def _save_token_to_db(service: str, bundle: OAuthTokenBundle) -> None:
    """Persist token into platform_tokens table so miniapp /api/social/status reflects it."""
    from datetime import datetime, timezone, timedelta
    try:
        expires_at = None
        if bundle.expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=bundle.expires_in)
        await upsert_token(
            platform=service,
            access_token=bundle.access_token,
            expires_at=expires_at,
            refresh_token=bundle.metadata.get("refresh_token", ""),
        )
        if bundle.user_id:
            await upsert_token(platform=f"{service}_user_id", access_token=str(bundle.user_id))
        if bundle.username:
            await upsert_token(platform=f"{service}_username", access_token=bundle.username)
        logger.info("Saved %s token to DB (user_id=%s)", service, bundle.user_id)
    except Exception:
        logger.exception("Failed to save %s token to DB", service)


def _exchange_bundle(service: str, code: str, *, code_verifier: str = "") -> OAuthTokenBundle:
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
    if service == "canva":
        return exchange_canva_code(
            code=code,
            client_id=settings.canva_client_id,
            client_secret=settings.canva_client_secret,
            redirect_uri=CANVA_REDIRECT_URI,
            code_verifier=code_verifier,
        )
    if service == "youtube":
        return exchange_youtube_code(
            code=code,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=YOUTUBE_REDIRECT_URI,
        )
    if service == "facebook":
        return exchange_facebook_code(
            code=code,
            client_id=settings.instagram_app_id,
            client_secret=settings.instagram_app_secret,
            redirect_uri=FACEBOOK_REDIRECT_URI,
        )
    raise OAuthExchangeError(f"Unsupported service: {service}")


def _notify_success(chat_id: str, bundle: OAuthTokenBundle) -> None:
    if bundle.service == "threads":
        text = (
            "✅ Threads подключён.\n"
            f"Аккаунт: @{bundle.username or 'unknown'}\n"
            f"User ID: {bundle.user_id}"
        )
    elif bundle.service == "canva":
        text = (
            "✅ Canva подключён.\n"
            f"User ID: {bundle.user_id}"
            + (f"\nИмя: {bundle.username}" if bundle.username else "")
        )
    elif bundle.service == "youtube":
        text = (
            "✅ YouTube подключён.\n"
            f"Канал: {bundle.username or 'unknown'}\n"
            f"Channel ID: {bundle.user_id}"
        )
    elif bundle.service == "facebook":
        ig_uid = bundle.metadata.get("ig_user_id", "")
        text = (
            "✅ Facebook Login подключён (Instagram Graph API).\n"
            + (f"IG аккаунт: @{bundle.username}\n" if bundle.username else "")
            + (f"IG User ID: {ig_uid}\n" if ig_uid else "")
            + "business_discovery и hashtag search теперь доступны."
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
