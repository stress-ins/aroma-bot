from __future__ import annotations

import asyncio
import contextvars
import logging
import threading
import time
from datetime import datetime, timezone

import anthropic

from config import settings

logger = logging.getLogger(__name__)

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

# Pricing per 1M tokens (USD)
_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
}
_DEFAULT_PRICING: dict[str, float] = {"input": 1.00, "output": 5.00}

# Context variable — set per-request by FastAPI auth dep or bot handlers
current_telegram_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_telegram_id", default=None
)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = _PRICING.get(model, _DEFAULT_PRICING)
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def _log_cost_sync(
    date: str,
    telegram_id: int | None,
    context: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    """Write cost log entry synchronously (called from daemon thread)."""
    from db.models import ApiCostLog
    from db.session import AsyncSessionLocal

    async def _write() -> None:
        async with AsyncSessionLocal() as session:
            entry = ApiCostLog(
                date=date,
                telegram_id=telegram_id,
                context=context,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                created_at=datetime.now(timezone.utc),
            )
            session.add(entry)
            await session.commit()

    try:
        asyncio.run(_write())
    except Exception as exc:
        logger.debug("Cost log write failed: %s", exc)


def _has_images(messages: list[dict]) -> bool:
    """Check if any message contains image content blocks."""
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            if any(c.get("type") == "image" for c in content if isinstance(c, dict)):
                return True
    return False


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

    # Primary: Replicate Claude (direct Claude API disabled — organization issue)
    if settings.replicate_api_key:
        # Route image requests to Gemini Vision
        use_vision = _has_images(messages)

        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                if use_vision:
                    text = _call_replicate_gemini_vision(
                        messages=messages, max_tokens=max_tokens, system=system, context=context,
                    )
                else:
                    text = _call_replicate_claude(
                        messages=messages, max_tokens=max_tokens, system=system, context=context,
                    )
                return text
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Replicate Claude attempt %d/%d failed for context=%s: %s",
                    attempt + 1, retries, context, exc,
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        notify_owner_throttled(
            f"\U0001f534 <b>Replicate Claude failed after {retries} attempts</b>\n"
            f"Context: {context}\nError: <code>{str(last_exc)[:200]}</code>",
            dedup_key=f"claude:replicate_failed:{context}",
        )
        raise last_exc  # type: ignore[misc]

    # Fallback: direct Claude API (currently disabled, kept for when org is restored)
    client = _get_client()
    kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
    if system:
        kwargs["system"] = system

    last_exc = None
    for attempt in range(retries):
        try:
            response = client.messages.create(**kwargs)
            text = response.content[0].text.strip()

            # Fire-and-forget cost logging
            try:
                usage = response.usage
                in_tok = getattr(usage, "input_tokens", 0)
                out_tok = getattr(usage, "output_tokens", 0)
                cost = _calc_cost(model, in_tok, out_tok)
                tid = current_telegram_id.get()
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                threading.Thread(
                    target=_log_cost_sync,
                    args=(today, tid, context, model, in_tok, out_tok, cost),
                    daemon=True,
                ).start()
            except Exception:
                logger.warning("claude_client: suppressed exception", exc_info=True)
                pass  # Never let logging break the LLM call

            return text

        except anthropic.BadRequestError as exc:
            last_exc = exc
            notify_owner_throttled(
                f"\U0001f4dd <b>Claude API BadRequest</b>\nContext: {context}\n"
                f"Error: <code>{type(exc).__name__}: {str(exc)[:200]}</code>",
                dedup_key=f"claude:bad_request:{context}",
            )
            break

        except anthropic.RateLimitError as exc:
            last_exc = exc
            logger.warning("Claude rate limit (attempt %d/%d, context=%s): %s", attempt + 1, retries, context, exc)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            continue

        except anthropic.APIConnectionError as exc:
            last_exc = exc
            logger.warning("Claude connection error (attempt %d/%d, context=%s): %s", attempt + 1, retries, context, exc)
            if attempt < retries - 1:
                time.sleep(1)
            continue

        except Exception as exc:
            last_exc = exc
            notify_owner_throttled(
                f"\U0001f4dd <b>Claude API error</b>\nContext: {context}\n"
                f"Error: <code>{type(exc).__name__}: {str(exc)[:200]}</code>",
                dedup_key=f"claude:{context}",
            )
            break
    else:
        notify_owner_throttled(
            f"\U0001f4dd <b>Claude API: all {retries} attempts exhausted</b>\n"
            f"Context: {context}\nError: <code>{str(last_exc)[:200]}</code>",
            dedup_key=f"claude:retry_exhausted:{context}",
        )

    raise last_exc  # type: ignore[misc]


def _call_replicate_claude(
    *,
    messages: list[dict],
    max_tokens: int,
    system: str = "",
    context: str = "Replicate Claude fallback",
) -> str:
    """Fallback: call Claude Haiku via Replicate prediction API."""
    import httpx

    # Build prompt from messages (Replicate uses prompt, not messages format)
    parts: list[str] = []
    for msg in messages:
        content = msg["content"]
        if isinstance(content, list):
            # Extract only text parts from multimodal messages
            text_parts = [
                c.get("text", "") for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            parts.append(" ".join(text_parts))
        else:
            parts.append(content)
    prompt = "\n\n".join(parts)

    payload: dict = {
        "input": {
            "prompt": prompt,
            "max_tokens": max(max_tokens, 1024),  # Replicate minimum is 1024
        },
    }
    if system:
        payload["input"]["system"] = system

    for _attempt in range(3):
        resp = httpx.post(
            "https://api.replicate.com/v1/models/anthropic/claude-4.5-haiku/predictions",
            headers={
                "Authorization": f"Token {settings.replicate_api_key}",
                "Content-Type": "application/json",
                "Prefer": "wait=60",
            },
            json=payload,
            timeout=65.0,
        )
        if resp.status_code == 429 and _attempt < 2:
            logger.warning("Replicate 429, retrying in 10s (attempt %d/3)", _attempt + 1)
            time.sleep(10)
            continue
        resp.raise_for_status()
        break
    data = resp.json()

    if data.get("status") != "succeeded":
        raise ValueError(f"Replicate prediction status: {data.get('status')}, error: {data.get('error')}")

    output = data.get("output", [])
    if isinstance(output, list):
        flat = []
        for item in output:
            if isinstance(item, list):
                flat.extend(str(s) for s in item)
            else:
                flat.append(str(item))
        text = "".join(flat).strip()
    else:
        text = str(output or "").strip()
    if not text:
        raise ValueError("Replicate Claude returned empty output")

    # Fire-and-forget cost logging
    try:
        tid = current_telegram_id.get()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        threading.Thread(
            target=_log_cost_sync,
            args=(today, tid, context, "claude-haiku-4.5/replicate", 0, 0, 0.0),
            daemon=True,
        ).start()
    except Exception:
        logger.warning("claude_client: suppressed exception", exc_info=True)
        pass

    return text


def _call_replicate_gemini_vision(
    *,
    messages: list[dict],
    max_tokens: int,
    system: str = "",
    context: str = "Replicate Gemini Vision",
) -> str:
    """Call Gemini 2.0 Flash via Replicate for multimodal (image+text) requests."""
    import httpx

    # Extract text and image from messages
    text_parts: list[str] = []
    image_uri: str | None = None
    if system:
        text_parts.append(system)

    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "image":
                    source = block.get("source", {})
                    if source.get("type") == "base64":
                        media_type = source.get("media_type", "image/png")
                        data = source.get("data", "")
                        image_uri = f"data:{media_type};base64,{data}"
        elif isinstance(content, str):
            text_parts.append(content)

    prompt = "\n\n".join(text_parts)

    input_payload: dict = {
        "prompt": prompt,
        "max_tokens": max(max_tokens, 1024),
    }
    if image_uri:
        input_payload["image"] = image_uri

    payload: dict = {"input": input_payload}

    for _attempt in range(3):
        resp = httpx.post(
            "https://api.replicate.com/v1/models/google/gemini-2.0-flash/predictions",
            headers={
                "Authorization": f"Token {settings.replicate_api_key}",
                "Content-Type": "application/json",
                "Prefer": "wait=90",
            },
            json=payload,
            timeout=95.0,
        )
        if resp.status_code == 429 and _attempt < 2:
            logger.warning("Replicate Gemini 429, retrying in 10s (attempt %d/3)", _attempt + 1)
            time.sleep(10)
            continue
        resp.raise_for_status()
        break

    data = resp.json()
    if data.get("status") != "succeeded":
        raise ValueError(f"Replicate Gemini prediction status: {data.get('status')}, error: {data.get('error')}")

    output = data.get("output", "")
    if isinstance(output, list):
        text = "".join(str(s) for s in output).strip()
    else:
        text = str(output or "").strip()
    if not text:
        raise ValueError("Replicate Gemini Vision returned empty output")

    # Fire-and-forget cost logging
    try:
        tid = current_telegram_id.get()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        threading.Thread(
            target=_log_cost_sync,
            args=(today, tid, context, "gemini-2.0-flash/replicate", 0, 0, 0.0),
            daemon=True,
        ).start()
    except Exception:
        logger.warning("claude_client: suppressed exception", exc_info=True)
        pass

    return text


