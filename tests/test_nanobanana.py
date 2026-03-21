"""Tests for image generation client (Kie.ai + NanoBanana fallback)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bot.services.gemini_images import ImageGenResult, generate_gemini_image_sync


def _make_settings(kie_key="test-kie-key", nano_key="", callback_base_url=""):
    s = MagicMock()
    s.kie_ai_api_key = kie_key
    s.nana_banana_api_key = nano_key
    s.image_api_key = kie_key or nano_key
    s.kie_callback_base_url = callback_base_url  # empty = polling mode (no webhook)
    return s


def _make_response(status_code=200, json_data=None, content=b""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code}", request=MagicMock(), response=resp
        )
    return resp


def _mock_client(responses):
    idx = {"i": 0}
    def factory(*args, **kwargs):
        c = MagicMock()
        def do_request(*a, **kw):
            r = responses[idx["i"]]
            idx["i"] += 1
            return r
        c.post = do_request
        c.get = do_request
        c.__enter__ = MagicMock(return_value=c)
        c.__exit__ = MagicMock(return_value=False)
        return c
    return factory


_SETTINGS_PATH = "bot.services.gemini_images.settings"
_CLIENT_PATH = "bot.services.gemini_images.httpx.Client"
_SLEEP_PATH = "bot.services.gemini_images.time.sleep"


class TestKieSubmitAndPollSuccess:
    def test_success(self):
        result_json = json.dumps({"resultUrls": ["https://cdn.example.com/img.png"]})
        responses = [
            _make_response(json_data={"code": 200, "data": {"taskId": "kie-123"}}),
            _make_response(json_data={"code": 200, "data": {"state": "generating"}}),
            _make_response(json_data={"code": 200, "data": {"state": "success", "resultJson": result_json}}),
            _make_response(content=b"\x89PNG" + b"\x00" * 200),
        ]
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH):
            result = generate_gemini_image_sync("test prompt")
        assert result.image_bytes is not None
        assert len(result.image_bytes) > 100
        assert result.kie_task_id == "kie-123"


class TestKieSubmitFailFallsBackToNano:
    def test_fallback(self):
        responses = [
            _make_response(status_code=500),
            _make_response(status_code=500),
            _make_response(json_data={"taskId": "nano-456"}),
            _make_response(json_data={"successFlag": 1, "resultImageUrl": "https://cdn.example.com/img.png"}),
            _make_response(content=b"\x89PNG" + b"\x00" * 200),
        ]
        with patch(_SETTINGS_PATH, _make_settings(kie_key="kie-key", nano_key="nano-key")), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH), \
             patch("bot.services.gemini_images._notify_image_failure"):
            result = generate_gemini_image_sync("test prompt")
        assert result.image_bytes is not None


class TestKiePollTimeout:
    def test_poll_timeout(self):
        responses = [_make_response(json_data={"code": 200, "data": {"taskId": "kie-123"}})]
        responses += [_make_response(json_data={"code": 200, "data": {"state": "generating"}})] * 5
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH), \
             patch("bot.services.gemini_images._POLL_MAX_ATTEMPTS", 3), \
             patch("bot.services.gemini_images._notify_image_failure"):
            result = generate_gemini_image_sync("test prompt")
        assert result.image_bytes is None


class TestKiePollFailState:
    def test_fail_state(self):
        responses = [
            _make_response(json_data={"code": 200, "data": {"taskId": "kie-123"}}),
            _make_response(json_data={"code": 200, "data": {"state": "fail", "failMsg": "content policy"}}),
        ]
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH), \
             patch("bot.services.gemini_images._notify_image_failure"):
            result = generate_gemini_image_sync("test prompt")
        assert result.image_bytes is None


class TestRetryOn429:
    def test_retry_429(self):
        result_json = json.dumps({"resultUrls": ["https://cdn.example.com/img.png"]})
        responses = [
            _make_response(status_code=429),
            _make_response(json_data={"code": 200, "data": {"taskId": "kie-123"}}),
            _make_response(json_data={"code": 200, "data": {"state": "success", "resultJson": result_json}}),
            _make_response(content=b"\x89PNG" + b"\x00" * 200),
        ]
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH):
            result = generate_gemini_image_sync("test prompt")
        assert result.image_bytes is not None


class TestNoApiKey:
    def test_no_key(self):
        with patch(_SETTINGS_PATH, _make_settings(kie_key="", nano_key="")):
            result = generate_gemini_image_sync("test prompt")
        assert result.image_bytes is None


class TestImageToImage:
    def test_image_urls_passed(self):
        captured = {}
        result_json = json.dumps({"resultUrls": ["https://cdn.example.com/img.png"]})
        responses = [
            _make_response(json_data={"code": 200, "data": {"taskId": "kie-123"}}),
            _make_response(json_data={"code": 200, "data": {"state": "success", "resultJson": result_json}}),
            _make_response(content=b"\x89PNG" + b"\x00" * 200),
        ]
        original_factory = _mock_client(responses)
        def capturing_factory(*args, **kwargs):
            c = original_factory(*args, **kwargs)
            original_post = c.post
            def capturing_post(*a, **kw):
                captured.update(kw.get("json", {}))
                return original_post(*a, **kw)
            c.post = capturing_post
            return c
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=capturing_factory), \
             patch(_SLEEP_PATH):
            generate_gemini_image_sync("edit this", image_urls=["https://example.com/photo.jpg"])
        assert captured.get("input", {}).get("image_input") == ["https://example.com/photo.jpg"]


class TestKieSnakeCaseResultUrls:
    """Test that snake_case result_urls from gpt-image models are parsed correctly."""
    def test_snake_case_result_urls(self):
        # gpt-image models return {"data": {"result_urls": [...]}, "code": 200} inside resultJson
        inner_result = json.dumps({"data": {"result_urls": ["https://cdn.example.com/gpt-img.png"]}, "code": 200})
        responses = [
            _make_response(json_data={"code": 200, "data": {"taskId": "kie-gpt-1"}}),
            _make_response(json_data={"code": 200, "data": {"state": "success", "resultJson": inner_result}}),
            _make_response(content=b"\x89PNG" + b"\x00" * 200),
        ]
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH):
            result = generate_gemini_image_sync("test prompt", model="gpt-image/1.5-text-to-image")
        assert result.image_bytes is not None
        assert result.kie_task_id == "kie-gpt-1"


class TestNanoBananaOnlySuccess:
    def test_nano_only(self):
        responses = [
            _make_response(json_data={"taskId": "nano-789"}),
            _make_response(json_data={"successFlag": 1, "resultImageUrl": "https://cdn.example.com/img.png"}),
            _make_response(content=b"\x89PNG" + b"\x00" * 200),
        ]
        with patch(_SETTINGS_PATH, _make_settings(kie_key="", nano_key="nano-key")), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH):
            result = generate_gemini_image_sync("test prompt")
        assert result.image_bytes is not None
