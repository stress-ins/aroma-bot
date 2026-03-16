from __future__ import annotations

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


_BASE_URL = "https://api.nanobananaapi.ai/api/v1/nanobanana"
_SUBMIT_TIMEOUT = 15
_POLL_TIMEOUT = 15
_DOWNLOAD_TIMEOUT = 30
_POLL_INITIAL_DELAY = 3
_POLL_INTERVAL = 4
_POLL_MAX_ATTEMPTS = 30
_SUBMIT_MAX_RETRIES = 2


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def generate_gemini_image_sync(
    prompt: str,
    *,
    aspect_ratio: str | None = None,
    log_context: str = "NanoBanana image",
) -> bytes | None:
    api_key = settings.image_api_key
    if not api_key:
        logger.warning("%s: no API key configured", log_context)
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "type": "TEXTTOIAMGE",
        "callBackUrl": "https://example.com/noop",
        "aspectRatio": aspect_ratio or "1:1",
        "resolution": "1K",
    }

    # Step 1: Submit task (retry on 429/5xx)
    task_id: str | None = None
    last_error = ""
    for attempt in range(_SUBMIT_MAX_RETRIES):
        try:
            with httpx.Client(timeout=_SUBMIT_TIMEOUT) as client:
                resp = client.post(f"{_BASE_URL}/generate-2", headers=headers, json=payload)
            if _is_retryable_status(resp.status_code) and attempt < _SUBMIT_MAX_RETRIES - 1:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("taskId") or data.get("data", {}).get("taskId")
            if not task_id:
                logger.warning("%s: no taskId in response: %s", log_context, str(data)[:200])
                _notify_image_failure(log_context, f"no taskId: {str(data)[:120]}")
                return None
            break
        except Exception as exc:
            last_error = str(exc)[:200]
            if attempt < _SUBMIT_MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
                continue
            logger.warning("%s submit error: %s", log_context, last_error)
            _notify_image_failure(log_context, last_error)
            return None

    if not task_id:
        logger.warning("%s: submit failed after retries: %s", log_context, last_error)
        _notify_image_failure(log_context, last_error)
        return None

    logger.info("%s: submitted taskId=%s", log_context, task_id)

    # Step 2: Poll for result
    time.sleep(_POLL_INITIAL_DELAY)
    for poll in range(_POLL_MAX_ATTEMPTS):
        try:
            with httpx.Client(timeout=_POLL_TIMEOUT) as client:
                resp = client.get(
                    f"{_BASE_URL}/record-info",
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
                image_url = (
                    data.get("resultImageUrl")
                    or data.get("resultImage")
                    or data.get("imageUrl")
                    or data.get("image_url")
                    or data.get("url")
                    or (data.get("result", {}).get("url") if isinstance(data.get("result"), dict) else None)
                )
                # Fallback: scan all string values for image URL
                if not image_url:
                    for v in data.values():
                        if isinstance(v, str) and ("http" in v) and any(
                            ext in v.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")
                        ):
                            image_url = v
                            break
                if not image_url:
                    logger.warning("%s: successFlag=1 but no image URL: %s", log_context, str(data)[:300])
                    _notify_image_failure(log_context, f"successFlag=1 but no image URL\n{str(data)[:200]}")
                    return None
                logger.info("%s: ready, downloading from %s", log_context, image_url[:80])
                return _download_image(image_url, log_context)

            if success_flag in (2, 3):
                logger.warning("%s: generation failed (flag=%s): %s", log_context, success_flag, str(data)[:200])
                _notify_image_failure(log_context, f"generation failed (flag={success_flag})")
                return None

            # successFlag == 0 or unknown → keep polling
        except Exception as exc:
            logger.debug("%s: poll error (attempt %d): %s", log_context, poll, str(exc)[:120])

        time.sleep(_POLL_INTERVAL)

    logger.warning("%s: poll timeout after %d attempts for taskId=%s", log_context, _POLL_MAX_ATTEMPTS, task_id)
    _notify_image_failure(log_context, f"poll timeout after {_POLL_MAX_ATTEMPTS} attempts")
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
