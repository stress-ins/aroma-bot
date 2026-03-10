from __future__ import annotations

import json
import os

CUSTOM_FILE = os.path.join(os.path.dirname(__file__), "custom.json")

FIELD_MAP = {
    "kw_ru": "keywords_ru",
    "kw_en": "keywords_en",
    "tag_ru": "hashtags_ru",
    "tag_en": "hashtags_en",
}

FIELD_LABELS = {
    "kw_ru": "🇷🇺 Слова RU",
    "kw_en": "🇬🇧 Слова EN",
    "tag_ru": "🏷 Хэштеги RU",
    "tag_en": "🏷 Хэштеги EN",
}


def _load() -> dict:
    if os.path.exists(CUSTOM_FILE):
        with open(CUSTOM_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"added": {}, "removed": {}}


def _save(data: dict) -> None:
    with open(CUSTOM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_word(topic_idx: int, field: str, word: str) -> None:
    data = _load()
    key = f"{topic_idx}:{field}"
    data["added"].setdefault(key, [])
    if word not in data["added"][key]:
        data["added"][key].append(word)
    removed = data["removed"].get(key, [])
    if word in removed:
        removed.remove(word)
    _save(data)


def remove_word(topic_idx: int, field: str, word: str) -> None:
    data = _load()
    key = f"{topic_idx}:{field}"
    data["removed"].setdefault(key, [])
    if word not in data["removed"][key]:
        data["removed"][key].append(word)
    added = data["added"].get(key, [])
    if word in added:
        added.remove(word)
    _save(data)
