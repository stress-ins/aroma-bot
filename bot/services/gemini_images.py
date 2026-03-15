from __future__ import annotations

import logging
import time

from config import settings

logger = logging.getLogger(__name__)


def _is_retryable_error(message: str) -> bool:
    normalized = message.upper()
    return any(token in normalized for token in ("429", "500", "502", "503", "504", "UNAVAILABLE", "DEADLINE"))


def generate_gemini_image_sync(
    prompt: str,
    *,
    aspect_ratio: str | None = None,
    log_context: str = "Gemini image",
) -> bytes | None:
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        logger.warning("%s import error: %s", log_context, str(exc)[:160])
        return None

    client = genai.Client(api_key=settings.image_api_key)
    last_error = ""
    for attempt in range(3):
        try:
            config_kwargs: dict = {"response_modalities": ["IMAGE", "TEXT"]}
            if aspect_ratio:
                config_kwargs["image_generation_config"] = types.ImageGenerationConfig(
                    aspect_ratio=aspect_ratio,
                )
            response = client.models.generate_content(
                model="gemini-3.1-flash-image-preview",
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            candidates = getattr(response, "candidates", []) or []
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", []) or []
                for part in parts:
                    inline_data = getattr(part, "inline_data", None)
                    if inline_data and getattr(inline_data, "data", None):
                        return inline_data.data
            last_error = "response_without_image"
        except Exception as exc:
            last_error = str(exc)[:160]
            if attempt < 2 and _is_retryable_error(last_error):
                time.sleep(1.5 * (attempt + 1))
                continue
            logger.warning("%s error: %s", log_context, last_error)
            return None

        if attempt < 2:
            time.sleep(1.0 * (attempt + 1))

    if last_error:
        logger.warning("%s error: %s", log_context, last_error)
    return None
