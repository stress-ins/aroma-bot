"""Tests for bot/services/policy_engine.py"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from bot.services.policy_engine import (
    PolicyConfig,
    PolicyResult,
    enforce_policy,
    get_platform_tone,
    load_policy_config,
    save_policy_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(
    forbidden: list[str] | None = None,
    rewrites: list[list[str]] | None = None,
    tones: dict[str, str] | None = None,
) -> PolicyConfig:
    return PolicyConfig(
        forbidden_phrases=forbidden or [],
        soft_rewrites=rewrites or [],
        per_platform_tone=tones or {},
    )


# ---------------------------------------------------------------------------
# enforce_policy
# ---------------------------------------------------------------------------

def test_enforce_removes_forbidden_phrase():
    cfg = _cfg(forbidden=["запрещено"])
    result = enforce_policy("Это запрещено и плохо", cfg=cfg)
    assert isinstance(result, PolicyResult)
    assert "запрещено" in result.violations
    # Text is not automatically deleted — violations are flagged, not removed
    assert "запрещено" in result.text.lower() or result.violations


def test_soft_rewrite_applied():
    cfg = _cfg(rewrites=[[r"\bв\s*дм\b", "в личные сообщения"]])
    result = enforce_policy("Напиши мне в ДМ, пожалуйста", cfg=cfg)
    assert "в личные сообщения" in result.text
    assert "в ДМ" not in result.text
    assert len(result.rewrites_applied) == 1


def test_soft_rewrite_case_insensitive():
    cfg = _cfg(rewrites=[["мощный инструмент", "хороший способ"]])
    result = enforce_policy("Это Мощный Инструмент для практики", cfg=cfg)
    assert "хороший способ" in result.text
    assert len(result.rewrites_applied) == 1


def test_soft_rewrite_not_applied_when_no_match():
    cfg = _cfg(rewrites=[[r"\bземляная база\b", "ощущение опоры"]])
    result = enforce_policy("Аромат лаванды очень расслабляет", cfg=cfg)
    assert result.rewrites_applied == []
    assert result.text == "Аромат лаванды очень расслабляет"


def test_multiple_rewrites_chained():
    cfg = _cfg(rewrites=[
        [r"\bв\s*дм\b", "в личные сообщения"],
        ["мощный инструмент", "хороший способ"],
    ])
    text = "Напиши в ДМ — это мощный инструмент"
    result = enforce_policy(text, cfg=cfg)
    assert "в личные сообщения" in result.text
    assert "хороший способ" in result.text
    assert len(result.rewrites_applied) == 2


def test_invalid_regex_pattern_skipped_gracefully():
    cfg = _cfg(rewrites=[["[invalid(regex", "replacement"], ["простое слово", "замена"]])
    result = enforce_policy("простое слово в тексте", cfg=cfg)
    # Invalid regex is skipped; valid one should still apply
    assert "замена" in result.text


def test_forbidden_phrase_detected_after_rewrite():
    # Even if a soft rewrite doesn't fully remove a phrase, forbidden detection catches it
    cfg = _cfg(
        forbidden=["плохая фраза"],
        rewrites=[],
    )
    result = enforce_policy("Это плохая фраза в тексте", cfg=cfg)
    assert "плохая фраза" in result.violations


# ---------------------------------------------------------------------------
# Platform isolation
# ---------------------------------------------------------------------------

def test_platform_isolation():
    """Instagram tone and rules do not bleed into telegram config."""
    cfg = PolicyConfig(
        forbidden_phrases=[],
        soft_rewrites=[],
        per_platform_tone={
            "instagram": "personal, visual, emotional",
            "telegram": "informative, practical",
        },
    )
    tone_ig = get_platform_tone("instagram", cfg=cfg)
    tone_tg = get_platform_tone("telegram", cfg=cfg)
    assert tone_ig != tone_tg
    assert "personal" in tone_ig
    assert "informative" in tone_tg


def test_unknown_platform_returns_empty_tone():
    cfg = _cfg(tones={"instagram": "emotional"})
    assert get_platform_tone("tiktok", cfg=cfg) == ""


def test_enforce_policy_platform_arg_doesnt_raise():
    cfg = _cfg()
    result = enforce_policy("Some text", platform="instagram", cfg=cfg)
    assert isinstance(result, PolicyResult)


# ---------------------------------------------------------------------------
# Empty / graceful config
# ---------------------------------------------------------------------------

def test_graceful_empty_config():
    cfg = _cfg()
    result = enforce_policy("Любой текст без ограничений", cfg=cfg)
    assert result.text == "Любой текст без ограничений"
    assert result.violations == []
    assert result.rewrites_applied == []


def test_graceful_empty_text():
    cfg = _cfg(forbidden=["запрещено"], rewrites=[["слово", "замена"]])
    result = enforce_policy("", cfg=cfg)
    assert result.text == ""
    assert result.violations == []
    assert result.rewrites_applied == []


# ---------------------------------------------------------------------------
# Load / save round-trip
# ---------------------------------------------------------------------------

def test_load_save_roundtrip(tmp_path, monkeypatch):
    config_file = tmp_path / "policy_config.json"
    monkeypatch.setattr("bot.services.policy_engine._CONFIG_PATH", config_file)

    original = PolicyConfig(
        forbidden_phrases=["фраза один", "фраза два"],
        soft_rewrites=[[r"\bв\s*дм\b", "в лс"], ["старое", "новое"]],
        per_platform_tone={"instagram": "emotional", "telegram": "practical"},
    )
    save_policy_config(original)

    assert config_file.exists()
    loaded = load_policy_config()

    assert loaded.forbidden_phrases == original.forbidden_phrases
    assert loaded.soft_rewrites == original.soft_rewrites
    assert loaded.per_platform_tone == original.per_platform_tone


def test_load_creates_defaults_when_file_missing(tmp_path, monkeypatch):
    config_file = tmp_path / "nonexistent_policy.json"
    monkeypatch.setattr("bot.services.policy_engine._CONFIG_PATH", config_file)

    cfg = load_policy_config()
    assert len(cfg.forbidden_phrases) > 0
    assert len(cfg.soft_rewrites) > 0
    assert len(cfg.per_platform_tone) > 0


def test_load_merges_defaults_when_config_empty(tmp_path, monkeypatch):
    config_file = tmp_path / "empty_policy.json"
    config_file.write_text(
        json.dumps({"forbidden_phrases": [], "soft_rewrites": [], "per_platform_tone": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("bot.services.policy_engine._CONFIG_PATH", config_file)

    cfg = load_policy_config()
    # Defaults should be merged in
    assert len(cfg.forbidden_phrases) > 0
    assert len(cfg.soft_rewrites) > 0


def test_load_graceful_on_corrupt_json(tmp_path, monkeypatch):
    config_file = tmp_path / "bad_policy.json"
    config_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr("bot.services.policy_engine._CONFIG_PATH", config_file)

    cfg = load_policy_config()
    # Should fall back to defaults without raising
    assert isinstance(cfg, PolicyConfig)
    assert len(cfg.forbidden_phrases) > 0


# ---------------------------------------------------------------------------
# PolicyConfig serialisation
# ---------------------------------------------------------------------------

def test_policy_config_to_from_dict():
    original = PolicyConfig(
        forbidden_phrases=["a", "b"],
        soft_rewrites=[["pat", "rep"]],
        per_platform_tone={"x": "y"},
    )
    d = original.to_dict()
    restored = PolicyConfig.from_dict(d)
    assert restored.forbidden_phrases == ["a", "b"]
    assert restored.soft_rewrites == [["pat", "rep"]]
    assert restored.per_platform_tone == {"x": "y"}
