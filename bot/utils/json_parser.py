"""Robust JSON extraction from Claude LLM responses.

Claude often wraps JSON in markdown fences or adds preamble text.
This module provides a single reusable function to handle all cases.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```")


def extract_json(raw: str, *, expect_array: bool = False) -> dict | list:
    """Extract a JSON object or array from a Claude response.

    Handles:
    - Pure JSON responses
    - JSON wrapped in ```json ... ``` markdown fences
    - JSON preceded/followed by preamble text
    - Multiple JSON blocks (returns first valid one)

    Args:
        raw: Raw text response from Claude.
        expect_array: If True, look for a JSON array ([...]) first.

    Returns:
        Parsed dict or list.

    Raises:
        ValueError: If no valid JSON found in the response.
    """
    text = raw.strip()
    if not text:
        raise ValueError("Empty response from Claude")

    # 1. Try markdown fence extraction first
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2. Try parsing the whole text as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Find JSON object or array by bracket matching
    open_char = "[" if expect_array else "{"
    close_char = "]" if expect_array else "}"

    start = text.find(open_char)
    if start == -1 and not expect_array:
        # Fallback: try array if object not found
        start = text.find("[")
        if start != -1:
            open_char, close_char = "[", "]"

    if start != -1:
        end = text.rfind(close_char)
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    # 4. If expect_array failed, try object
    if expect_array:
        start = text.find("{")
        if start != -1:
            end = text.rfind("}")
            if end > start:
                try:
                    result = json.loads(text[start:end + 1])
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass

    raise ValueError(f"No valid JSON found in Claude response: {text[:200]}...")
