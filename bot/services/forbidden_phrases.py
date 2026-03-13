"""Forbidden phrases — backward-compat wrapper delegating to PolicyEngine."""
from __future__ import annotations

from bot.services.policy_engine import load_policy_config, save_policy_config


def load_forbidden_phrases() -> list[str]:
    return load_policy_config().forbidden_phrases


def save_forbidden_phrases(phrases: list[str]) -> None:
    cfg = load_policy_config()
    cfg.forbidden_phrases = phrases
    save_policy_config(cfg)


def add_forbidden_phrase(phrase: str) -> list[str]:
    phrase = phrase.strip()
    cfg = load_policy_config()
    if phrase and phrase not in cfg.forbidden_phrases:
        cfg.forbidden_phrases.append(phrase)
        save_policy_config(cfg)
    return cfg.forbidden_phrases


def remove_forbidden_phrase(phrase: str) -> list[str]:
    phrase = phrase.strip()
    cfg = load_policy_config()
    cfg.forbidden_phrases = [p for p in cfg.forbidden_phrases if p != phrase]
    save_policy_config(cfg)
    return cfg.forbidden_phrases
