"""PolicyEngine — unified brand voice enforcement for all content platforms."""
from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("data/policy_config.json")

_DEFAULT_FORBIDDEN_PHRASES = [
    "голова не отключается",
    "кажется, что ничего не помогает",
    "твоему телу нужен сигнал",
    "запах это первое что замечает нервную систему",
    "у каждого свой аромат",
    "земляная база",
    "в ДМ",
]

_DEFAULT_SOFT_REWRITES: list[list[str]] = [
    [r"\bв\s*дм\b", "в личные сообщения"],
    [r"земляная база", "ощущение опоры под ногами"],
    [r"твоему телу нужен сигнал", "телу важно почувствовать, что можно выдохнуть"],
    [r"запах это первое что замечает нервную систему", "аромат тело замечает почти сразу"],
    [r"кажется,\s*что ничего не помогает", "ты уже многое пробовала, а напряжение все равно держится"],
]

_DEFAULT_PLATFORM_TONE = {
    "instagram": "personal, visual, emotional",
    "telegram": "informative, practical",
    "threads": "conversational, punchy",
}


@dataclass
class PolicyConfig:
    forbidden_phrases: list[str] = field(default_factory=list)
    soft_rewrites: list[list[str]] = field(default_factory=list)   # [[pattern, replacement], ...]
    per_platform_tone: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "forbidden_phrases": self.forbidden_phrases,
            "soft_rewrites": self.soft_rewrites,
            "per_platform_tone": self.per_platform_tone,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyConfig:
        return cls(
            forbidden_phrases=list(data.get("forbidden_phrases", [])),
            soft_rewrites=[list(r) for r in data.get("soft_rewrites", [])],
            per_platform_tone=dict(data.get("per_platform_tone", {})),
        )


@dataclass
class PolicyResult:
    text: str
    violations: list[str] = field(default_factory=list)      # found forbidden phrases
    rewrites_applied: list[str] = field(default_factory=list)  # applied substitutions


def load_policy_config() -> PolicyConfig:
    """Load policy config from JSON, merging with defaults."""
    if not _CONFIG_PATH.exists():
        return PolicyConfig(
            forbidden_phrases=list(_DEFAULT_FORBIDDEN_PHRASES),
            soft_rewrites=[list(r) for r in _DEFAULT_SOFT_REWRITES],
            per_platform_tone=dict(_DEFAULT_PLATFORM_TONE),
        )
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        cfg = PolicyConfig.from_dict(data)
        # Merge defaults: add default forbidden phrases if config list is empty
        if not cfg.forbidden_phrases:
            cfg.forbidden_phrases = list(_DEFAULT_FORBIDDEN_PHRASES)
        if not cfg.soft_rewrites:
            cfg.soft_rewrites = [list(r) for r in _DEFAULT_SOFT_REWRITES]
        if not cfg.per_platform_tone:
            cfg.per_platform_tone = dict(_DEFAULT_PLATFORM_TONE)
        return cfg
    except Exception as exc:
        logger.warning("PolicyEngine: failed to load config: %s", exc)
        return PolicyConfig(
            forbidden_phrases=list(_DEFAULT_FORBIDDEN_PHRASES),
            soft_rewrites=[list(r) for r in _DEFAULT_SOFT_REWRITES],
            per_platform_tone=dict(_DEFAULT_PLATFORM_TONE),
        )


def save_policy_config(cfg: PolicyConfig) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def enforce_policy(
    text: str,
    platform: str = "",
    cfg: PolicyConfig | None = None,
) -> PolicyResult:
    """
    Apply policy to text:
    1. Apply soft rewrites (regex substitutions)
    2. Flag remaining forbidden phrases as violations
    Returns PolicyResult with possibly modified text.
    """
    if cfg is None:
        cfg = load_policy_config()

    result_text = text
    rewrites_applied: list[str] = []
    violations: list[str] = []

    # 1. Apply soft rewrites
    for rewrite in cfg.soft_rewrites:
        if len(rewrite) < 2:
            continue
        pattern, replacement = rewrite[0], rewrite[1]
        try:
            new_text, count = re.subn(pattern, replacement, result_text, flags=re.IGNORECASE)
            if count > 0:
                rewrites_applied.append(f"{pattern!r} → {replacement!r}")
                result_text = new_text
        except re.error as exc:
            logger.warning("PolicyEngine: invalid rewrite pattern %r: %s", pattern, exc)

    # 2. Detect remaining forbidden phrase violations (case-insensitive)
    for phrase in cfg.forbidden_phrases:
        if phrase.lower() in result_text.lower():
            violations.append(phrase)

    return PolicyResult(text=result_text, violations=violations, rewrites_applied=rewrites_applied)


def get_platform_tone(platform: str, cfg: PolicyConfig | None = None) -> str:
    """Return tone description for a given platform."""
    if cfg is None:
        cfg = load_policy_config()
    return cfg.per_platform_tone.get(platform, "")
