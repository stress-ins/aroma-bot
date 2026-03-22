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
    "threads_read_replies",
    "threads_manage_mentions",
)

INSTAGRAM_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_LONG_LIVED_TOKEN_URL = "https://graph.instagram.com/access_token"
INSTAGRAM_ME_URL = "https://graph.instagram.com/me"
INSTAGRAM_DEFAULT_SCOPES = (
    "instagram_business_basic",
    "instagram_business_content_publish",
)

YOUTUBE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
)

CANVA_AUTHORIZE_URL = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
CANVA_ME_URL = "https://api.canva.com/rest/v1/users/me"
CANVA_PROFILE_URL = "https://api.canva.com/rest/v1/users/me/profile"
CANVA_DEFAULT_SCOPES = (
    "profile:read",
    "design:content:read",
    "design:content:write",
    "design:meta:read",
    "asset:read",
    "asset:write",
    "brandtemplate:meta:read",
    "brandtemplate:content:read",
    "brandtemplate:content:write",
    "comment:read",
    "comment:write",
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
    code_verifier: str = ""


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
        "enable_fb_login": "0",
        "force_authentication": "1",
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
    # Use /consent/ endpoint directly instead of /oauth/authorize.
    # On iOS, Universal Links intercept instagram.com/oauth/authorize and open
    # the Instagram app which can't handle it. The /consent/ URL with
    # flow=ig_biz_login_oauth bypasses this by going straight to the consent page.
    import json as _json
    import uuid
    params_json = _json.dumps({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": "-".join(scopes),
        "logger_id": str(uuid.uuid4()),
        "app_id": client_id,
        "platform_app_id": client_id,
    })
    consent_params = {
        "flow": "ig_biz_login_oauth",
        "params_json": params_json,
        "source": "oauth_permissions_page_www",
    }
    return f"https://www.instagram.com/consent/?{urlencode(consent_params)}"


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
        token_response = session.post(
            INSTAGRAM_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        short_payload = _parse_json_response(token_response, "Instagram code exchange")
        short_token = str(short_payload.get("access_token", "")).strip()
        if not short_token:
            raise OAuthExchangeError("Instagram code exchange did not return access_token")
        user_id = str(short_payload.get("user_id", "")).strip()

        long_response = session.get(
            INSTAGRAM_LONG_LIVED_TOKEN_URL,
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": client_secret,
                "access_token": short_token,
            },
        )
        long_payload = _parse_json_response(long_response, "Instagram long-lived token exchange")
        long_token = str(long_payload.get("access_token", "")).strip()
        if not long_token:
            raise OAuthExchangeError("Instagram long-lived exchange did not return access_token")

        username = ""
        try:
            profile_response = session.get(
                INSTAGRAM_ME_URL,
                params={
                    "fields": "user_id,username",
                    "access_token": long_token,
                },
            )
            profile_payload = _parse_json_response(profile_response, "Instagram profile lookup")
            username = str(profile_payload.get("username", "")).strip()
            user_id = str(profile_payload.get("user_id") or profile_payload.get("id") or user_id).strip()
        except OAuthExchangeError:
            pass

        if not user_id:
            raise OAuthExchangeError("Instagram exchange did not return user id")

        return OAuthTokenBundle(
            service="instagram",
            short_lived_token=short_token,
            access_token=long_token,
            expires_in=_coerce_int(long_payload.get("expires_in")),
            user_id=user_id,
            username=username,
        )

    if client is not None:
        return _work(client)
    with httpx.Client(timeout=30.0) as session:
        return _work(session)


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    import os
    code_verifier = _urlsafe_b64encode(os.urandom(32))
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = _urlsafe_b64encode(digest)
    return code_verifier, code_challenge


def build_canva_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    scopes: tuple[str, ...] = CANVA_DEFAULT_SCOPES,
) -> tuple[str, str]:
    """Build Canva OAuth authorize URL with PKCE.

    Returns (authorize_url, code_verifier).
    """
    code_verifier, code_challenge = _generate_pkce_pair()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "code_challenge_method": "s256",
        "code_challenge": code_challenge,
    }
    return f"{CANVA_AUTHORIZE_URL}?{urlencode(params)}", code_verifier


def exchange_canva_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str,
    client: httpx.Client | None = None,
) -> OAuthTokenBundle:
    def _work(session: httpx.Client) -> OAuthTokenBundle:
        token_response = session.post(
            CANVA_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            auth=(client_id, client_secret),
        )
        token_payload = _parse_json_response(token_response, "Canva code exchange")
        access_token = str(token_payload.get("access_token", "")).strip()
        if not access_token:
            raise OAuthExchangeError("Canva code exchange did not return access_token")

        profile_response = session.get(
            CANVA_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        profile_payload = _parse_json_response(profile_response, "Canva profile lookup")
        # Canva /users/me returns {"team_user": {"user_id": "...", "team_id": "..."}}
        team_user = profile_payload.get("team_user") or {}
        user_id = str(
            team_user.get("user_id", "")
            or profile_payload.get("id", "")
        ).strip()
        # /users/me doesn't return display_name — fetch from /users/me/profile
        display_name = ""
        try:
            name_response = session.get(
                CANVA_PROFILE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            name_payload = _parse_json_response(name_response, "Canva profile name")
            display_name = str(
                (name_payload.get("profile") or {}).get("display_name", "")
            ).strip()
        except Exception:
            pass
        # Fallback: extract user_id from access_token JWT sub claim
        if not user_id:
            try:
                jwt_body = access_token.split(".")[1]
                claims = json.loads(_urlsafe_b64decode(jwt_body).decode("utf-8"))
                user_id = str(claims.get("sub", "")).strip()
            except Exception:
                pass
        if not user_id:
            raise OAuthExchangeError(f"Canva profile lookup did not return user id: {profile_payload}")

        return OAuthTokenBundle(
            service="canva",
            short_lived_token=access_token,
            access_token=access_token,
            expires_in=_coerce_int(token_payload.get("expires_in")),
            user_id=user_id,
            username=display_name,
            metadata={
                "refresh_token": str(token_payload.get("refresh_token", "")).strip(),
            },
        )

    if client is not None:
        return _work(client)
    with httpx.Client(timeout=30.0) as session:
        return _work(session)


def refresh_canva_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    client: httpx.Client | None = None,
) -> dict[str, str | int]:
    """Refresh a Canva access token. Returns dict with access_token, refresh_token, expires_in."""
    def _work(session: httpx.Client) -> dict[str, str | int]:
        resp = session.post(
            CANVA_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(client_id, client_secret),
        )
        payload = _parse_json_response(resp, "Canva token refresh")
        new_access = str(payload.get("access_token", "")).strip()
        if not new_access:
            raise OAuthExchangeError("Canva refresh did not return access_token")
        return {
            "access_token": new_access,
            "refresh_token": str(payload.get("refresh_token", "")).strip(),
            "expires_in": _coerce_int(payload.get("expires_in")) or 0,
        }

    if client is not None:
        return _work(client)
    with httpx.Client(timeout=30.0) as session:
        return _work(session)


def build_youtube_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str = "",
    scopes: tuple[str, ...] = YOUTUBE_DEFAULT_SCOPES,
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{YOUTUBE_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_youtube_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    client: httpx.Client | None = None,
) -> OAuthTokenBundle:
    def _work(session: httpx.Client) -> OAuthTokenBundle:
        token_response = session.post(
            YOUTUBE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        token_payload = _parse_json_response(token_response, "YouTube code exchange")
        access_token = str(token_payload.get("access_token", "")).strip()
        if not access_token:
            raise OAuthExchangeError("YouTube code exchange did not return access_token")

        refresh_token = str(token_payload.get("refresh_token", "")).strip()

        # Fetch channel info
        channel_response = session.get(
            YOUTUBE_CHANNELS_URL,
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        channel_payload = _parse_json_response(channel_response, "YouTube channel lookup")
        items = channel_payload.get("items", [])
        if not items:
            raise OAuthExchangeError("YouTube account has no channels")
        channel = items[0]
        channel_id = str(channel.get("id", "")).strip()
        channel_title = str(channel.get("snippet", {}).get("title", "")).strip()

        return OAuthTokenBundle(
            service="youtube",
            short_lived_token=access_token,
            access_token=access_token,
            expires_in=_coerce_int(token_payload.get("expires_in")),
            user_id=channel_id,
            username=channel_title,
            metadata={"refresh_token": refresh_token},
        )

    if client is not None:
        return _work(client)
    with httpx.Client(timeout=30.0) as session:
        return _work(session)


def refresh_youtube_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    client: httpx.Client | None = None,
) -> dict[str, str | int]:
    """Refresh a YouTube/Google access token."""
    def _work(session: httpx.Client) -> dict[str, str | int]:
        resp = session.post(
            YOUTUBE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        payload = _parse_json_response(resp, "YouTube token refresh")
        new_access = str(payload.get("access_token", "")).strip()
        if not new_access:
            raise OAuthExchangeError("YouTube refresh did not return access_token")
        return {
            "access_token": new_access,
            "refresh_token": refresh_token,  # Google doesn't rotate refresh tokens
            "expires_in": _coerce_int(payload.get("expires_in")) or 0,
        }

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


def build_oauth_state(*, secret: str, service: str, chat_id: int | str, user_id: int | str, code_verifier: str = "") -> str:
    payload: dict[str, Any] = {
        "service": service,
        "chat_id": str(chat_id),
        "user_id": str(user_id),
        "issued_at": int(time.time()),
    }
    if code_verifier:
        payload["code_verifier"] = code_verifier
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

    code_verifier = str(payload.get("code_verifier", "")).strip()
    return OAuthConnectState(service=service, chat_id=chat_id, user_id=user_id, issued_at=issued_at, code_verifier=code_verifier)


def extract_state_payload_unsafe(state: str) -> dict:
    """Decode state payload without verifying HMAC signature.

    Returns raw dict or empty dict on any failure.
    """
    try:
        encoded_body = state.split(".", 1)[0]
        body = _urlsafe_b64decode(encoded_body)
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {}


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
        }
    if bundle.service == "canva":
        return {}
    if bundle.service == "youtube":
        updates: dict[str, str] = {
            "GOOGLE_REFRESH_TOKEN": bundle.metadata.get("refresh_token", ""),
        }
        if bundle.user_id:
            updates["YOUTUBE_CHANNEL_ID"] = bundle.user_id
        return updates
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
