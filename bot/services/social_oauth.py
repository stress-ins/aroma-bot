from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx


THREADS_AUTHORIZE_URL = "https://www.threads.net/oauth/authorize"
THREADS_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
THREADS_LONG_LIVED_TOKEN_URL = "https://graph.threads.net/access_token"
THREADS_ME_URL = "https://graph.threads.net/me"
THREADS_DEFAULT_SCOPES = (
    "threads_basic",
    "threads_content_publish",
    "threads_manage_replies",
    "threads_manage_insights",
)

INSTAGRAM_AUTHORIZE_URL = "https://www.facebook.com/dialog/oauth"
INSTAGRAM_TOKEN_URL = "https://graph.facebook.com/oauth/access_token"
INSTAGRAM_LONG_LIVED_TOKEN_URL = "https://graph.facebook.com/oauth/access_token"
INSTAGRAM_ME_ACCOUNTS_URL = "https://graph.facebook.com/me/accounts"
INSTAGRAM_DEFAULT_SCOPES = (
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
)


class OAuthExchangeError(RuntimeError):
    pass


class OAuthStateError(RuntimeError):
    pass


@dataclass
class OAuthTokenBundle:
    service: str
    short_lived_token: str
    access_token: str
    expires_in: int | None
    user_id: str
    username: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OAuthConnectState:
    service: str
    chat_id: str
    user_id: str
    issued_at: int


def build_threads_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str = "",
    scopes: tuple[str, ...] = THREADS_DEFAULT_SCOPES,
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ",".join(scopes),
    }
    if state:
        params["state"] = state
    return f"{THREADS_AUTHORIZE_URL}?{urlencode(params)}"


def build_instagram_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str = "",
    scopes: tuple[str, ...] = INSTAGRAM_DEFAULT_SCOPES,
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ",".join(scopes),
    }
    if state:
        params["state"] = state
    return f"{INSTAGRAM_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_threads_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    client: httpx.Client | None = None,
) -> OAuthTokenBundle:
    def _work(session: httpx.Client) -> OAuthTokenBundle:
        token_response = session.post(
            THREADS_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        short_payload = _parse_json_response(token_response, "Threads code exchange")
        short_token = str(short_payload.get("access_token", "")).strip()
        if not short_token:
            raise OAuthExchangeError("Threads code exchange did not return access_token")

        long_response = session.get(
            THREADS_LONG_LIVED_TOKEN_URL,
            params={
                "grant_type": "th_exchange_token",
                "client_secret": client_secret,
                "access_token": short_token,
            },
        )
        long_payload = _parse_json_response(long_response, "Threads long-lived token exchange")
        long_token = str(long_payload.get("access_token", "")).strip()
        if not long_token:
            raise OAuthExchangeError("Threads long-lived exchange did not return access_token")

        profile_response = session.get(
            THREADS_ME_URL,
            params={"fields": "id,username,name"},
            headers={"Authorization": f"Bearer {long_token}"},
        )
        profile_payload = _parse_json_response(profile_response, "Threads profile lookup")
        user_id = str(profile_payload.get("id", "")).strip()
        if not user_id:
            raise OAuthExchangeError("Threads profile lookup did not return user id")

        return OAuthTokenBundle(
            service="threads",
            short_lived_token=short_token,
            access_token=long_token,
            expires_in=_coerce_int(long_payload.get("expires_in")),
            user_id=user_id,
            username=str(profile_payload.get("username", "")).strip(),
            metadata={"name": str(profile_payload.get("name", "")).strip()},
        )

    if client is not None:
        return _work(client)
    with httpx.Client(timeout=30.0) as session:
        return _work(session)


def exchange_instagram_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    client: httpx.Client | None = None,
) -> OAuthTokenBundle:
    def _work(session: httpx.Client) -> OAuthTokenBundle:
        token_response = session.get(
            INSTAGRAM_TOKEN_URL,
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        short_payload = _parse_json_response(token_response, "Instagram code exchange")
        user_token = str(short_payload.get("access_token", "")).strip()
        if not user_token:
            raise OAuthExchangeError("Instagram code exchange did not return access_token")
        facebook_user_id = str(short_payload.get("user_id", "")).strip()

        long_response = session.get(
            INSTAGRAM_LONG_LIVED_TOKEN_URL,
            params={
                "grant_type": "fb_exchange_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "fb_exchange_token": user_token,
            },
        )
        long_payload = _parse_json_response(long_response, "Instagram long-lived user token exchange")
        long_user_token = str(long_payload.get("access_token", "")).strip()
        if not long_user_token:
            raise OAuthExchangeError("Instagram long-lived user token exchange did not return access_token")

        pages_response = session.get(
            INSTAGRAM_ME_ACCOUNTS_URL,
            params={
                "fields": "id,name,access_token,instagram_business_account{id,username}",
                "access_token": long_user_token,
            },
        )
        pages_payload = _parse_json_response(pages_response, "Instagram page lookup")
        pages = pages_payload.get("data")
        if not isinstance(pages, list):
            raise OAuthExchangeError("Instagram page lookup did not return pages")

        selected_page: dict[str, Any] | None = None
        selected_account: dict[str, Any] | None = None
        for item in pages:
            if not isinstance(item, dict):
                continue
            business_account = item.get("instagram_business_account")
            if isinstance(business_account, dict) and str(business_account.get("id", "")).strip():
                selected_page = item
                selected_account = business_account
                break

        if not selected_page or not selected_account:
            raise OAuthExchangeError(
                "Instagram page lookup did not find a connected instagram_business_account. "
                "Проверьте, что Instagram Business/Creator аккаунт привязан к Facebook Page."
            )

        page_token = str(selected_page.get("access_token", "")).strip()
        business_account_id = str(selected_account.get("id", "")).strip()
        if not page_token:
            raise OAuthExchangeError("Instagram page lookup did not return page access token")
        if not business_account_id:
            raise OAuthExchangeError("Instagram page lookup did not return instagram_business_account id")

        return OAuthTokenBundle(
            service="instagram",
            short_lived_token=user_token,
            access_token=page_token,
            expires_in=_coerce_int(long_payload.get("expires_in")),
            user_id=business_account_id,
            username=str(selected_account.get("username", "")).strip(),
            metadata={
                "facebook_user_id": facebook_user_id,
                "page_id": str(selected_page.get("id", "")).strip(),
                "page_name": str(selected_page.get("name", "")).strip(),
                "instagram_business_account_id": business_account_id,
            },
        )

    if client is not None:
        return _work(client)
    with httpx.Client(timeout=30.0) as session:
        return _work(session)


def update_env_file(env_path: str | Path, updates: dict[str, str]) -> None:
    path = Path(env_path)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(updates)
    rendered_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            rendered_lines.append(line)
            continue
        key, _, _value = line.partition("=")
        key = key.strip()
        if key in pending:
            rendered_lines.append(f"{key}={pending.pop(key)}")
        else:
            rendered_lines.append(line)

    for key, value in pending.items():
        rendered_lines.append(f"{key}={value}")

    output = "\n".join(rendered_lines).rstrip() + "\n"
    path.write_text(output, encoding="utf-8")


def build_oauth_state(*, secret: str, service: str, chat_id: int | str, user_id: int | str) -> str:
    payload = {
        "service": service,
        "chat_id": str(chat_id),
        "user_id": str(user_id),
        "issued_at": int(time.time()),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return _urlsafe_b64encode(body) + "." + _urlsafe_b64encode(signature)


def parse_oauth_state(*, state: str, secret: str, max_age_seconds: int = 3600) -> OAuthConnectState:
    try:
        encoded_body, encoded_signature = state.split(".", 1)
    except ValueError as exc:
        raise OAuthStateError("Malformed OAuth state") from exc

    body = _urlsafe_b64decode(encoded_body)
    signature = _urlsafe_b64decode(encoded_signature)
    expected_signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise OAuthStateError("Invalid OAuth state signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthStateError("Invalid OAuth state payload") from exc

    issued_at = _coerce_int(payload.get("issued_at"))
    if issued_at is None:
        raise OAuthStateError("OAuth state is missing issued_at")
    if int(time.time()) - issued_at > max_age_seconds:
        raise OAuthStateError("OAuth state expired")

    service = str(payload.get("service", "")).strip()
    chat_id = str(payload.get("chat_id", "")).strip()
    user_id = str(payload.get("user_id", "")).strip()
    if not service or not chat_id or not user_id:
        raise OAuthStateError("OAuth state is incomplete")

    return OAuthConnectState(service=service, chat_id=chat_id, user_id=user_id, issued_at=issued_at)


def bundle_env_updates(bundle: OAuthTokenBundle) -> dict[str, str]:
    if bundle.service == "threads":
        return {
            "THREADS_ACCESS_TOKEN": bundle.access_token,
            "THREADS_USER_ID": bundle.user_id,
            "THREADS_USERNAME": bundle.username,
        }
    if bundle.service == "instagram":
        return {
            "INSTAGRAM_ACCESS_TOKEN": bundle.access_token,
            "INSTAGRAM_USER_ID": bundle.user_id,
            "INSTAGRAM_BUSINESS_ACCOUNT_ID": str(
                bundle.metadata.get("instagram_business_account_id") or bundle.user_id
            ),
        }
    raise OAuthExchangeError(f"Unsupported service: {bundle.service}")


def notify_telegram_chat(*, bot_token: str, chat_id: str, text: str, client: httpx.Client | None = None) -> None:
    if not bot_token or not chat_id:
        return

    def _work(session: httpx.Client) -> None:
        response = session.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        response.raise_for_status()

    if client is not None:
        _work(client)
        return
    with httpx.Client(timeout=15.0) as session:
        _work(session)


def _parse_json_response(response: httpx.Response, context: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise OAuthExchangeError(f"{context} returned non-JSON response: {response.text[:200]}") from exc

    if response.status_code >= 400:
        raise OAuthExchangeError(f"{context} failed with {response.status_code}: {_stringify_error(payload)}")
    if isinstance(payload, dict) and payload.get("error"):
        raise OAuthExchangeError(f"{context} failed: {_stringify_error(payload['error'])}")
    if not isinstance(payload, dict):
        raise OAuthExchangeError(f"{context} returned unexpected payload: {payload!r}")
    return payload


def _stringify_error(value: Any) -> str:
    if isinstance(value, dict):
        message = value.get("message")
        if message:
            return str(message)
        return str(value)
    return str(value)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _urlsafe_b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + padding)
    except (ValueError, base64.binascii.Error) as exc:
        raise OAuthStateError("Invalid OAuth state encoding") from exc
