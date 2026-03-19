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
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_write())
        loop.close()
    except Exception as exc:
        logger.debug("Cost log write failed: %s", exc)


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
                pass  # Never let logging break the LLM call

            return text

        except anthropic.BadRequestError as exc:
            # Non-retryable (e.g. "organization disabled") → go straight to fallback
            last_exc = exc
            notify_owner_throttled(
                f"\U0001f4dd <b>Claude API BadRequest</b>\nContext: {context}\n"
                f"Error: <code>{type(exc).__name__}: {str(exc)[:200]}</code>",
                dedup_key=f"claude:bad_request:{context}",
            )
            break

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
    else:
        notify_owner_throttled(
            f"\U0001f4dd <b>Claude API: all {retries} attempts exhausted</b>\n"
            f"Context: {context}\nError: <code>{str(last_exc)[:200]}</code>",
            dedup_key=f"claude:retry_exhausted:{context}",
        )

    # Fallback: Kie.ai Gemini (Kie.ai Claude endpoint is broken — returns empty content)
    if settings.kie_ai_api_key:
        logger.warning("Claude API failed, falling back to Kie.ai Gemini for context=%s", context)
        try:
            text = _call_kie_gemini(messages=messages, max_tokens=max_tokens, system=system, context=context)
            notify_owner_throttled(
                f"\u26a0\ufe0f <b>Claude fallback \u2192 Kie.ai Gemini</b>\nContext: {context}\n"
                f"Claude error: <code>{str(last_exc)[:150]}</code>",
                dedup_key=f"claude:fallback_kie_gemini:{context}",
            )
            return text
        except Exception as gemini_exc:
            logger.exception("Kie.ai Gemini fallback also failed for context=%s", context)
            notify_owner_throttled(
                f"\U0001f534 <b>All LLM providers failed</b>\nContext: {context}\n"
                f"Claude: <code>{str(last_exc)[:100]}</code>\n"
                f"Kie Gemini: <code>{str(gemini_exc)[:100]}</code>",
                dedup_key=f"claude:all_failed:{context}",
            )

    raise last_exc  # type: ignore[misc]


def _call_kie_claude(
    *,
    messages: list[dict],
    max_tokens: int,
    system: str = "",
    model: str = "claude-haiku-4-5-20251001",
    context: str = "Kie Claude fallback",
) -> str:
    """Fallback: call Claude via Kie.ai Anthropic-compatible API."""
    client = anthropic.Anthropic(
        base_url="https://api.kie.ai/claude",
        api_key=settings.kie_ai_api_key,
    )
    kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    blocks = response.content if response.content else []
    text = (blocks[0].text or "").strip() if blocks and hasattr(blocks[0], "text") else ""
    if not text:
        raise ValueError(f"Kie.ai Claude returned empty/null content (blocks={len(blocks)})")

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
            args=(today, tid, context, f"{model}/kie", in_tok, out_tok, cost),
            daemon=True,
        ).start()
    except Exception:
        pass

    return text


def _call_kie_gemini(
    *,
    messages: list[dict],
    max_tokens: int,
    system: str = "",
    context: str = "Kie Gemini fallback",
) -> str:
    """Fallback: call Gemini 2.5 Flash via Kie.ai OpenAI-compatible API."""
    import httpx

    api_messages: list[dict] = []
    if system:
        api_messages.append({"role": "system", "content": system})
    for msg in messages:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    resp = httpx.post(
        "https://api.kie.ai/gemini-2.5-flash/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.kie_ai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "messages": api_messages,
            "stream": False,
            "include_thoughts": False,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError(f"Kie.ai Gemini returned no choices: {data}")
    content = (choices[0].get("message") or {}).get("content")
    text = (content or "").strip()
    if not text:
        raise ValueError("Kie.ai Gemini returned empty response")

    # Fire-and-forget cost logging
    try:
        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        cost = (in_tok * 0.15 + out_tok * 0.60) / 1_000_000
        tid = current_telegram_id.get()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        threading.Thread(
            target=_log_cost_sync,
            args=(today, tid, context, "gemini-2.5-flash/kie", in_tok, out_tok, cost),
            daemon=True,
        ).start()
    except Exception:
        pass

    return text
