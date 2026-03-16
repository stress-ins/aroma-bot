from __future__ import annotations

from config import settings


def call_claude(
    *,
    messages: list[dict],
    max_tokens: int,
    system: str = "",
    model: str = "claude-haiku-4-5-20251001",
    context: str = "Claude API",
) -> str:
    """Thin Claude wrapper — notifies owner on failure, then re-raises."""
    import anthropic

    from bot.handlers.monitor import notify_owner_throttled

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
    if system:
        kwargs["system"] = system
    try:
        response = client.messages.create(**kwargs)
        return response.content[0].text.strip()
    except Exception as exc:
        notify_owner_throttled(
            f"\U0001f4dd <b>Claude API error</b>\nContext: {context}\n"
            f"Error: <code>{type(exc).__name__}: {str(exc)[:200]}</code>",
            dedup_key=f"claude:{context}",
        )
        raise
