from __future__ import annotations

import json
from pathlib import Path

_PATH = Path("data/forbidden_phrases.json")


def load_forbidden_phrases() -> list[str]:
    if not _PATH.exists():
        return []
    return json.loads(_PATH.read_text(encoding="utf-8"))


def save_forbidden_phrases(phrases: list[str]) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(phrases, ensure_ascii=False, indent=2), encoding="utf-8")


def add_forbidden_phrase(phrase: str) -> list[str]:
    phrases = load_forbidden_phrases()
    phrase = phrase.strip()
    if phrase and phrase not in phrases:
        phrases.append(phrase)
        save_forbidden_phrases(phrases)
    return phrases


def remove_forbidden_phrase(phrase: str) -> list[str]:
    phrases = [p for p in load_forbidden_phrases() if p != phrase.strip()]
    save_forbidden_phrases(phrases)
    return phrases
