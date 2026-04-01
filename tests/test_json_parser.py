"""Tests for bot.utils.json_parser — robust JSON extraction from Claude responses."""

from __future__ import annotations

import json

import pytest

from bot.utils.json_parser import extract_json


def test_pure_json_object():
    raw = '{"score": 0.85, "issues": []}'
    result = extract_json(raw)
    assert result == {"score": 0.85, "issues": []}


def test_pure_json_array():
    raw = '[{"index": 1, "caption": "test"}]'
    result = extract_json(raw, expect_array=True)
    assert isinstance(result, list)
    assert result[0]["caption"] == "test"


def test_markdown_fence_json():
    raw = '```json\n{"score": 0.9}\n```'
    result = extract_json(raw)
    assert result["score"] == 0.9


def test_markdown_fence_no_lang():
    raw = '```\n{"score": 0.9}\n```'
    result = extract_json(raw)
    assert result["score"] == 0.9


def test_preamble_before_json():
    raw = 'Here is the result:\n\n{"score": 0.85, "issues": ["problem 1"]}'
    result = extract_json(raw)
    assert result["score"] == 0.85


def test_preamble_before_array():
    raw = 'Generated posts:\n[{"index": 1, "caption": "Hello"}]'
    result = extract_json(raw, expect_array=True)
    assert isinstance(result, list)
    assert result[0]["caption"] == "Hello"


def test_text_after_json():
    raw = '{"score": 0.9}\n\nHope this helps!'
    result = extract_json(raw)
    assert result["score"] == 0.9


def test_empty_string_raises():
    with pytest.raises(ValueError, match="Empty response"):
        extract_json("")


def test_no_json_raises():
    with pytest.raises(ValueError, match="No valid JSON"):
        extract_json("This is just plain text with no JSON at all")


def test_nested_json():
    data = {"outline": {"positions": [{"index": 1}]}, "summary": "test"}
    raw = json.dumps(data)
    result = extract_json(raw)
    assert result["outline"]["positions"][0]["index"] == 1


def test_expect_array_fallback_to_object():
    raw = '{"score": 0.9}'
    result = extract_json(raw, expect_array=True)
    assert result["score"] == 0.9
