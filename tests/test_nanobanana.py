"""Tests for NanoBanana image generation client."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from bot.services.gemini_images import generate_gemini_image_sync


def _make_settings(api_key="test-key-123"):
    s = MagicMock()
    s.image_api_key = api_key
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
    """Create a mock httpx.Client context manager that returns responses in order."""
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


class TestSubmitAndPollSuccess:
    def test_success(self):
        responses = [
            _make_response(json_data={"taskId": "abc-123"}),
            _make_response(json_data={"successFlag": 0}),
            _make_response(json_data={"successFlag": 1, "resultImageUrl": "https://cdn.example.com/img.png"}),
            _make_response(content=b"\x89PNG" + b"\x00" * 200),
        ]
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH):
            result = generate_gemini_image_sync("test prompt")
        assert result is not None
        assert len(result) > 100


class TestSubmitFailure:
    def test_submit_failure(self):
        responses = [
            _make_response(status_code=500),
            _make_response(status_code=500),
        ]
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH):
            result = generate_gemini_image_sync("test prompt")
        assert result is None


class TestPollTimeout:
    def test_poll_timeout(self):
        responses = [_make_response(json_data={"taskId": "abc-123"})]
        responses += [_make_response(json_data={"successFlag": 0})] * 5

        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH), \
             patch("bot.services.gemini_images._POLL_MAX_ATTEMPTS", 3):
            result = generate_gemini_image_sync("test prompt")
        assert result is None


class TestPollFailureFlag:
    def test_poll_failure_flag(self):
        responses = [
            _make_response(json_data={"taskId": "abc-123"}),
            _make_response(json_data={"successFlag": 2}),
        ]
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH):
            result = generate_gemini_image_sync("test prompt")
        assert result is None


class TestAspectRatioDefault:
    def test_default_aspect_ratio(self):
        captured = {}
        responses = [
            _make_response(json_data={"taskId": "abc-123"}),
            _make_response(json_data={"successFlag": 1, "resultImageUrl": "https://cdn.example.com/img.png"}),
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
            generate_gemini_image_sync("test prompt")
        assert captured.get("aspectRatio") == "1:1"


class TestRetryOn429:
    def test_retry_429(self):
        responses = [
            _make_response(status_code=429),
            _make_response(json_data={"taskId": "abc-123"}),
            _make_response(json_data={"successFlag": 1, "resultImageUrl": "https://cdn.example.com/img.png"}),
            _make_response(content=b"\x89PNG" + b"\x00" * 200),
        ]
        with patch(_SETTINGS_PATH, _make_settings()), \
             patch(_CLIENT_PATH, side_effect=_mock_client(responses)), \
             patch(_SLEEP_PATH):
            result = generate_gemini_image_sync("test prompt")
        assert result is not None


class TestNoApiKey:
    def test_no_key(self):
        with patch(_SETTINGS_PATH, _make_settings(api_key="")):
            result = generate_gemini_image_sync("test prompt")
        assert result is None
