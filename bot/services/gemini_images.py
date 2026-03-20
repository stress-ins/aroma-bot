from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ImageGenResult:
    """Structured result from image generation."""
    image_bytes: bytes | None = None
    kie_task_id: str | None = None
    error: str | None = None
    image_url: str | None = None


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


def _extract_kie_image_url(data: dict) -> str | None:
    """Extract image URL from KIE response data (shared by poll and callback)."""
    inner = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    state = inner.get("state") or data.get("state", "")
    if state != "success":
        return None
    result_json_raw = inner.get("resultJson") or data.get("resultJson", "")
    try:
        result_obj = json.loads(result_json_raw) if isinstance(result_json_raw, str) else result_json_raw
    except (json.JSONDecodeError, TypeError):
        result_obj = {}
    urls: list[str] = []
    if isinstance(result_obj, dict):
        urls = result_obj.get("resultUrls", [])
        if not urls:
            inner_data = result_obj.get("data", {})
            if isinstance(inner_data, dict):
                urls = inner_data.get("result_urls", []) or inner_data.get("resultUrls", [])
    if urls:
        return urls[0]
    for src in (inner, data):
        for key in ("resultImageUrl", "resultImage", "imageUrl", "url"):
            if src.get(key):
                return src[key]
    return None


def _kie_submit(
    prompt: str,
    headers: dict[str, str],
    aspect_ratio: str,
    image_urls: list[str] | None,
    log_context: str,
    model: str | None = None,
    callback_url: str = "",
) -> str | None:
    """Submit a task to Kie.ai. Returns taskId or None."""
    model_id = model or _KIE_MODEL
    if model_id.startswith("gpt-image/"):
        ratio_map = _KIE_GPT_IMAGE_RATIO_MAP
    else:
        ratio_map = _KIE_ASPECT_RATIO_MAP
    ar = ratio_map.get(aspect_ratio, aspect_ratio)
    task_type = "IMAGETOIMAGE" if image_urls else "TEXTTOIMAGE"
    input_block: dict[str, object] = {
        "prompt": prompt,
        "aspect_ratio": ar,
        "resolution": "1K",
        "output_format": "png",
    }
    if model_id.startswith("gpt-image/"):
        input_block["quality"] = "medium"
    if image_urls:
        input_block["image_input"] = image_urls

    payload: dict[str, object] = {
        "model": model or _KIE_MODEL,
        "type": task_type,
        "callBackUrl": callback_url,
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


def _kie_poll(
    task_id: str,
    headers: dict[str, str],
    log_context: str,
    *,
    task_id_for_db_check: str | None = None,
) -> str | None:
    """Poll Kie.ai for task result. Returns image URL or None.

    If *task_id_for_db_check* is set, every 5 iterations (~20 s) check the DB
    to see if the webhook callback already delivered the result.
    """
    _DB_CHECK_INTERVAL = 5  # every 5 poll iterations

    time.sleep(_POLL_INITIAL_DELAY)
    for poll in range(_POLL_MAX_ATTEMPTS):
        # --- DB short-circuit: callback may have arrived ---
        if task_id_for_db_check and poll > 0 and poll % _DB_CHECK_INTERVAL == 0:
            try:
                from bot.services.kie_task_store import get_task_sync
                db_task = get_task_sync(task_id_for_db_check)
                if db_task and db_task.status == "success" and db_task.image_url:
                    logger.info("%s: callback already delivered for %s, skipping poll", log_context, task_id)
                    return db_task.image_url
            except Exception:
                pass  # DB check is best-effort

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
                url = _extract_kie_image_url(data)
                if url:
                    return url
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
        "callBackUrl": "",
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
    draft_id: str | None = None,
    content_type: str = "",
    slot_key: str = "",
) -> ImageGenResult:
    """Generate an image. Uses Kie.ai (primary) with NanoBanana fallback.

    Returns ImageGenResult with image_bytes and kie_task_id (if applicable).
    When draft_id + content_type are provided, the task is registered in DB
    so the webhook callback can deliver the result without polling.
    """
    kie_key = settings.kie_ai_api_key
    nano_key = settings.nana_banana_api_key
    if not kie_key and not nano_key:
        logger.warning("%s: no image API key configured", log_context)
        return ImageGenResult(error="no image API key configured")

    ar = aspect_ratio or "1:1"

    # Build callback URL if configured
    callback_url = ""
    base = settings.kie_callback_base_url.strip().rstrip("/")
    if base:
        callback_url = f"{base}/api/webhooks/kie-callback"

    # --- Primary: Kie.ai ---
    kie_task_id: str | None = None
    if kie_key:
        headers = {"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"}
        kie_task_id = _kie_submit(prompt, headers, ar, image_urls, log_context, model=model, callback_url=callback_url)
        if kie_task_id:
            logger.info("%s: Kie submitted taskId=%s (callback=%s)", log_context, kie_task_id, bool(callback_url))
            # Register in DB for callback tracking
            if draft_id and content_type:
                from bot.services.kie_task_store import register_task_sync
                register_task_sync(
                    kie_task_id,
                    draft_id=draft_id,
                    content_type=content_type,
                    slot_key=slot_key,
                    prompt=prompt[:4000],
                    aspect_ratio=ar,
                    model=model or _KIE_MODEL,
                )
            db_check_id = kie_task_id if (draft_id and content_type) else None
            image_url = _kie_poll(kie_task_id, headers, log_context, task_id_for_db_check=db_check_id)
            if image_url:
                img_bytes = _download_image(image_url, log_context)
                if img_bytes:
                    return ImageGenResult(image_bytes=img_bytes, kie_task_id=kie_task_id, image_url=image_url)
        logger.warning("%s: Kie.ai failed, trying NanoBanana fallback", log_context)

    # --- Fallback: NanoBanana direct API ---
    if nano_key:
        headers = {"Authorization": f"Bearer {nano_key}", "Content-Type": "application/json"}
        img_bytes = _nano_generate(prompt, headers, ar, log_context)
        if img_bytes:
            return ImageGenResult(image_bytes=img_bytes)

    _notify_image_failure(log_context, "all providers failed")
    return ImageGenResult(kie_task_id=kie_task_id, error="all providers failed")


def recover_kie_task_sync(task_id: str) -> ImageGenResult:
    """Re-poll a KIE task by ID and download the result if available."""
    kie_key = settings.kie_ai_api_key
    if not kie_key:
        return ImageGenResult(kie_task_id=task_id, error="no KIE API key configured")

    headers = {"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"}
    log_context = f"recover:{task_id[:8]}"

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

        if state != "success":
            return ImageGenResult(kie_task_id=task_id, error=f"task state: {state}")

        image_url = _extract_kie_image_url(data)
        if not image_url:
            return ImageGenResult(kie_task_id=task_id, error="success but no image URL in response")

        img_bytes = _download_image(image_url, log_context)
        if img_bytes:
            return ImageGenResult(image_bytes=img_bytes, kie_task_id=task_id, image_url=image_url)
        return ImageGenResult(kie_task_id=task_id, error="download failed", image_url=image_url)

    except Exception as exc:
        logger.warning("recover %s error: %s", task_id, str(exc)[:200])
        return ImageGenResult(kie_task_id=task_id, error=str(exc)[:200])


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
