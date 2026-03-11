from __future__ import annotations

import logging

from config import settings

logger = logging.getLogger(__name__)


def generate_gemini_image_sync(prompt: str, *, log_context: str = "Gemini image") -> bytes | None:
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.image_api_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"]
            ),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                return part.inline_data.data
    except Exception as exc:
        logger.warning("%s error: %s", log_context, str(exc)[:160])
    return None
