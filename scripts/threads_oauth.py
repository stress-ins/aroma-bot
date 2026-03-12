from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.services.social_oauth import build_threads_authorize_url, exchange_threads_code, update_env_file
from config import settings


DEFAULT_REDIRECT_URI = "https://oauth.aromara.ru/threads/callback"


def main() -> int:
    parser = argparse.ArgumentParser(description="Threads OAuth helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("authorize-url", help="Print the Threads authorization URL")
    auth_parser.add_argument("--client-id", default=os.getenv("THREADS_APP_ID") or settings.threads_app_id)
    auth_parser.add_argument("--redirect-uri", default=os.getenv("THREADS_REDIRECT_URI", DEFAULT_REDIRECT_URI))
    auth_parser.add_argument("--state", default="")

    exchange_parser = subparsers.add_parser("exchange-code", help="Exchange a Threads code for tokens")
    exchange_parser.add_argument("--code", required=True)
    exchange_parser.add_argument("--client-id", default=os.getenv("THREADS_APP_ID") or settings.threads_app_id)
    exchange_parser.add_argument(
        "--client-secret",
        default=os.getenv("THREADS_APP_SECRET") or settings.threads_app_secret,
    )
    exchange_parser.add_argument("--redirect-uri", default=os.getenv("THREADS_REDIRECT_URI", DEFAULT_REDIRECT_URI))
    exchange_parser.add_argument("--env-file", default=".env")
    exchange_parser.add_argument("--no-write-env", action="store_true")

    args = parser.parse_args()
    if args.command == "authorize-url":
        _require_value(args.client_id, "THREADS_APP_ID / --client-id")
        print(
            build_threads_authorize_url(
                client_id=args.client_id,
                redirect_uri=args.redirect_uri,
                state=args.state,
            )
        )
        return 0

    _require_value(args.client_id, "THREADS_APP_ID / --client-id")
    _require_value(args.client_secret, "THREADS_APP_SECRET / --client-secret")
    bundle = exchange_threads_code(
        code=args.code,
        client_id=args.client_id,
        client_secret=args.client_secret,
        redirect_uri=args.redirect_uri,
    )
    payload = {
        "service": bundle.service,
        "user_id": bundle.user_id,
        "username": bundle.username,
        "expires_in": bundle.expires_in,
        "access_token": bundle.access_token,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not args.no_write_env:
        update_env_file(
            args.env_file,
            {
                "THREADS_ACCESS_TOKEN": bundle.access_token,
                "THREADS_USER_ID": bundle.user_id,
                "THREADS_USERNAME": bundle.username,
            },
        )
        print(f"Updated {args.env_file} with THREADS_ACCESS_TOKEN / THREADS_USER_ID / THREADS_USERNAME")
    return 0


def _require_value(value: str, label: str) -> None:
    if value.strip():
        return
    raise SystemExit(f"Missing {label}")


if __name__ == "__main__":
    sys.exit(main())
