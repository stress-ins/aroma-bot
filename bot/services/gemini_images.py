from __future__ import annotations

import json
import logging
import time

import httpx

from config import settings

logger = logging.getLogger(__name__)


def _notify_image_failure(log_context: str, error: str) -> None:
    from bot.handlers.monitor import notify_owner_throttled

    notify_owner_throttled(
        f"\U0001f5bc <b>Image gen failed</b>\nContext: {log_context}\n"
        f"Error: <code>{error}</code>",
        dedup_key=f"img:{log_context}",
    )


# ---------------------------------------------------------------------------
# Kie.ai unified API (primary provider)
# ---------------------------------------------------------------------------
_KIE_BASE_URL = "https://api.kie.ai/api/v1/jobs"
_KIE_MODEL = "google/nano-banana"  # Gemini 2.5 Flash Image Preview

# ---------------------------------------------------------------------------
# Legacy NanoBanana direct API (fallback)
# ---------------------------------------------------------------------------
_NANO_BASE_URL = "https://api.nanobananaapi.ai/api/v1/nanobanana"

_SUBMIT_TIMEOUT = 15
_POLL_TIMEOUT = 15
_DOWNLOAD_TIMEOUT = 30
_POLL_INITIAL_DELAY = 3
_POLL_INTERVAL = 4
_POLL_MAX_ATTEMPTS = 30
_SUBMIT_MAX_RETRIES = 2


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


# ---------------------------------------------------------------------------
# Kie.ai provider
# ---------------------------------------------------------------------------


_KIE_ASPECT_RATIO_MAP: dict[str, str] = {
    "4:5": "3:4",    # default fallback for models without 4:5
    "5:4": "4:3",
}

# gpt-image models only support 1:1, 2:3, 3:2
_KIE_GPT_IMAGE_RATIO_MAP: dict[str, str] = {
    "4:5": "2:3",
    "3:4": "2:3",
    "5:4": "3:2",
    "4:3": "3:2",
    "9:16": "2:3",
    "16:9": "3:2",
}


def _kie_submit(
    prompt: str,
    headers: dict[str, str],
    aspect_ratio: str,
    image_urls: list[str] | None,
    log_context: str,
    model: str | None = None,
) -> str | None:
    """Submit a task to Kie.ai. Returns taskId or None."""
    model_id = model or _KIE_MODEL
    if model_id.startswith("gpt-image/"):
        ratio_map = _KIE_GPT_IMAGE_RATIO_MAP
    else:
        ratio_map = _KIE_ASPECT_RATIO_MAP
    ar = ratio_map.get(aspect_ratio, aspect_ratio)
    input_block: dict[str, object] = {
        "prompt": prompt,
        "aspect_ratio": ar,
        "resolution": "1K",
        "output_format": "png",
    }
    if image_urls:
        input_block["image_input"] = image_urls

    payload: dict[str, object] = {
        "model": model or _KIE_MODEL,
        "callBackUrl": "https://example.com/noop",
        "input": input_block,
    }

    last_error = ""
    for attempt in range(_SUBMIT_MAX_RETRIES):
        try:
            with httpx.Client(timeout=_SUBMIT_TIMEOUT) as client:
                resp = client.post(f"{_KIE_BASE_URL}/createTask", headers=headers, json=payload)
            if _is_retryable_status(resp.status_code) and attempt < _SUBMIT_MAX_RETRIES - 1:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            api_code = data.get("code")
            if api_code and api_code != 200:
                msg = data.get("msg", "unknown API error")
                logger.warning("%s: Kie API error code=%s: %s", log_context, api_code, msg)
                _notify_image_failure(log_context, f"Kie API error {api_code}: {msg}")
                return None
            inner = data.get("data")
            task_id = (inner.get("taskId") if isinstance(inner, dict) else None) or data.get("taskId")
            if not task_id:
                logger.warning("%s: no taskId in Kie response: %s", log_context, str(data)[:200])
                _notify_image_failure(log_context, f"no taskId: {str(data)[:120]}")
                return None
            return task_id
        except Exception as exc:
            last_error = str(exc)[:200]
            if attempt < _SUBMIT_MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
                continue
            logger.warning("%s Kie submit error: %s", log_context, last_error)
            _notify_image_failure(log_context, last_error)
            return None

    logger.warning("%s: Kie submit failed after retries: %s", log_context, last_error)
    _notify_image_failure(log_context, last_error)
    return None


def _kie_poll(task_id: str, headers: dict[str, str], log_context: str) -> str | None:
    """Poll Kie.ai for task result. Returns image URL or None."""
    time.sleep(_POLL_INITIAL_DELAY)
    for poll in range(_POLL_MAX_ATTEMPTS):
        try:
            with httpx.Client(timeout=_POLL_TIMEOUT) as client:
                resp = client.get(
                    f"{_KIE_BASE_URL}/recordInfo",
                    headers=headers,
                    params={"taskId": task_id},
                )
            resp.raise_for_status()
            data = resp.json()
            inner = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
            state = inner.get("state") or data.get("state", "")

            if state == "success":
                result_json_raw = inner.get("resultJson") or data.get("resultJson", "")
                try:
                    result_obj = json.loads(result_json_raw) if isinstance(result_json_raw, str) else result_json_raw
                except (json.JSONDecodeError, TypeError):
                    result_obj = {}
                urls = result_obj.get("resultUrls", []) if isinstance(result_obj, dict) else []
                if urls:
                    return urls[0]
                # Fallback: check known URL fields
                for src in (inner, data):
                    for key in ("resultImageUrl", "resultImage", "imageUrl", "url"):
                        if src.get(key):
                            return src[key]
                logger.warning("%s: Kie success but no image URL: %s", log_context, str(data)[:300])
                _notify_image_failure(log_context, f"success but no image URL\n{str(data)[:200]}")
                return None

            if state == "fail":
                fail_msg = inner.get("failMsg") or data.get("failMsg", "unknown")
                logger.warning("%s: Kie generation failed: %s", log_context, fail_msg)
                _notify_image_failure(log_context, f"Kie generation failed: {fail_msg}")
                return None

            # waiting / queuing / generating -> keep polling
        except Exception as exc:
            logger.debug("%s: Kie poll error (attempt %d): %s", log_context, poll, str(exc)[:120])

        time.sleep(_POLL_INTERVAL)

    logger.warning("%s: Kie poll timeout after %d attempts for taskId=%s", log_context, _POLL_MAX_ATTEMPTS, task_id)
    _notify_image_failure(log_context, f"Kie poll timeout after {_POLL_MAX_ATTEMPTS} attempts")
    return None


# ---------------------------------------------------------------------------
# Legacy NanoBanana provider (fallback)
# ---------------------------------------------------------------------------


def _nano_generate(
    prompt: str,
    headers: dict[str, str],
    aspect_ratio: str,
    log_context: str,
) -> bytes | None:
    """Full submit+poll+download via legacy NanoBanana direct API."""
    payload = {
        "prompt": prompt,
        "type": "TEXTTOIAMGE",
        "callBackUrl": "https://example.com/noop",
        "aspectRatio": aspect_ratio,
        "resolution": "1K",
        "outputFormat": "png",
    }

    task_id: str | None = None
    last_error = ""
    for attempt in range(_SUBMIT_MAX_RETRIES):
        try:
            with httpx.Client(timeout=_SUBMIT_TIMEOUT) as client:
                resp = client.post(f"{_NANO_BASE_URL}/generate", headers=headers, json=payload)
            if _is_retryable_status(resp.status_code) and attempt < _SUBMIT_MAX_RETRIES - 1:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            api_code = data.get("code")
            if api_code and api_code != 200:
                msg = data.get("msg", "unknown API error")
                logger.warning("%s: NanoBanana API error code=%s: %s", log_context, api_code, msg)
                return None
            inner = data.get("data")
            task_id = data.get("taskId") or (inner.get("taskId") if isinstance(inner, dict) else None)
            if not task_id:
                logger.warning("%s: no taskId in NanoBanana response: %s", log_context, str(data)[:200])
                return None
            break
        except Exception as exc:
            last_error = str(exc)[:200]
            if attempt < _SUBMIT_MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
                continue
            logger.warning("%s NanoBanana submit error: %s", log_context, last_error)
            return None

    if not task_id:
        return None

    logger.info("%s: NanoBanana submitted taskId=%s", log_context, task_id)

    time.sleep(_POLL_INITIAL_DELAY)
    for poll in range(_POLL_MAX_ATTEMPTS):
        try:
            with httpx.Client(timeout=_POLL_TIMEOUT) as client:
                resp = client.get(
                    f"{_NANO_BASE_URL}/record-info",
                    headers=headers,
                    params={"taskId": task_id},
                )
            resp.raise_for_status()
            data = resp.json()
            success_flag = data.get("successFlag")
            if success_flag is None:
                inner = data.get("data", {})
                success_flag = inner.get("successFlag")
                data = inner if inner else data

            if success_flag == 1:
                inner_data = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
                image_url = (
                    data.get("resultImageUrl")
                    or data.get("resultImage")
                    or inner_data.get("resultImageUrl")
                    or inner_data.get("resultImage")
                )
                if not image_url:
                    _IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
                    for src in (data, inner_data):
                        for v in src.values():
                            if isinstance(v, str) and ("http" in v) and any(ext in v.lower() for ext in _IMAGE_EXTS):
                                image_url = v
                                break
                        if image_url:
                            break
                if not image_url:
                    return None
                return _download_image(image_url, log_context)

            if success_flag in (2, 3):
                return None

        except Exception as exc:
            logger.debug("%s: NanoBanana poll error (attempt %d): %s", log_context, poll, str(exc)[:120])

        time.sleep(_POLL_INTERVAL)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_gemini_image_sync(
    prompt: str,
    *,
    aspect_ratio: str | None = None,
    image_urls: list[str] | None = None,
    log_context: str = "image",
    model: str | None = None,
) -> bytes | None:
    """Generate an image. Uses Kie.ai (primary) with NanoBanana fallback.

    Args:
        prompt: Text description for the image.
        aspect_ratio: e.g. "1:1", "4:5", "9:16".
        image_urls: Optional list of source image URLs for image-to-image editing.
        log_context: Label for logs/alerts.
        model: Kie.ai model ID override (e.g. "gpt-image/1.5-text-to-image").
    """
    kie_key = settings.kie_ai_api_key
    nano_key = settings.nana_banana_api_key
    if not kie_key and not nano_key:
        logger.warning("%s: no image API key configured", log_context)
        return None

    ar = aspect_ratio or "1:1"

    # --- Primary: Kie.ai ---
    if kie_key:
        headers = {"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"}
        task_id = _kie_submit(prompt, headers, ar, image_urls, log_context, model=model)
        if task_id:
            logger.info("%s: Kie submitted taskId=%s", log_context, task_id)
            image_url = _kie_poll(task_id, headers, log_context)
            if image_url:
                result = _download_image(image_url, log_context)
                if result:
                    return result
        logger.warning("%s: Kie.ai failed, trying NanoBanana fallback", log_context)

    # --- Fallback: NanoBanana direct API ---
    if nano_key:
        headers = {"Authorization": f"Bearer {nano_key}", "Content-Type": "application/json"}
        result = _nano_generate(prompt, headers, ar, log_context)
        if result:
            return result

    _notify_image_failure(log_context, "all providers failed")
    return None


def _download_image(url: str, log_context: str) -> bytes | None:
    try:
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url)
        resp.raise_for_status()
        data = resp.content
        if len(data) < 100:
            logger.warning("%s: downloaded image too small (%d bytes)", log_context, len(data))
            _notify_image_failure(log_context, f"downloaded image too small ({len(data)} bytes)")
            return None
        return data
    except Exception as exc:
        logger.warning("%s: download error: %s", log_context, str(exc)[:200])
        _notify_image_failure(log_context, str(exc)[:200])
        return None
