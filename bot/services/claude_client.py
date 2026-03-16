from __future__ import annotations

import time

import anthropic

from config import settings

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def call_claude(
    *,
    messages: list[dict],
    max_tokens: int,
    system: str = "",
    model: str = "claude-haiku-4-5-20251001",
    context: str = "Claude API",
    retries: int = 3,
) -> str:
    """Claude wrapper with retry, rate-limit handling and notify_owner."""
    from bot.handlers.monitor import notify_owner_throttled

    client = _get_client()
    kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
    if system:
        kwargs["system"] = system

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.messages.create(**kwargs)
            return response.content[0].text.strip()

        except anthropic.RateLimitError as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            continue

        except anthropic.APIConnectionError as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(1)
            continue

        except Exception as exc:
            notify_owner_throttled(
                f"\U0001f4dd <b>Claude API error</b>\nContext: {context}\n"
                f"Error: <code>{type(exc).__name__}: {str(exc)[:200]}</code>",
                dedup_key=f"claude:{context}",
            )
            raise

    notify_owner_throttled(
        f"\U0001f4dd <b>Claude API: all {retries} attempts exhausted</b>\n"
        f"Context: {context}\nError: <code>{str(last_exc)[:200]}</code>",
        dedup_key=f"claude:retry_exhausted:{context}",
    )
    raise last_exc  # type: ignore[misc]
