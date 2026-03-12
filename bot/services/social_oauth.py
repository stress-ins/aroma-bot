from __future__ import annotations

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

INSTAGRAM_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_LONG_LIVED_TOKEN_URL = "https://graph.instagram.com/access_token"
INSTAGRAM_ME_URL = "https://graph.instagram.com/me"
INSTAGRAM_DEFAULT_SCOPES = (
    "instagram_business_basic",
    "instagram_business_content_publish",
)


class OAuthExchangeError(RuntimeError):
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
        "enable_fb_login": "0",
        "force_authentication": "1",
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
