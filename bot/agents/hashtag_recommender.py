"""Hashtag Recommender agent: suggest hashtags for wellness/aromatherapy content."""

from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "hashtag_seed.json"
_seed_cache: list[dict] | None = None


def _load_seed() -> list[dict]:
    global _seed_cache
    if _seed_cache is not None:
        return _seed_cache
    if _SEED_PATH.exists():
        _seed_cache = json.loads(_SEED_PATH.read_text())
        return _seed_cache
    return []


def _extract_themes_sync(text: str, platform: str) -> list[str]:
    """Extract themes from post text via Claude."""
    from bot.agents.prompts.hashtag_prompts import extract_themes_prompt
    from bot.services.claude_client import call_claude
    from bot.utils.json_parser import extract_json

    prompt = extract_themes_prompt(text, platform)
    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        context="hashtag_themes",
    )

    # Try JSON first
    try:
        data = extract_json(raw)
        if isinstance(data, dict):
            raw_themes = data.get("themes", [])
            if isinstance(raw_themes, list):
                themes = []
                for t in raw_themes:
                    parts = [p.strip().lower() for p in str(t).split("|")]
                    themes.extend(parts)
                if themes:
                    return themes
    except (ValueError, TypeError):
        pass

    # Legacy fallback
    themes = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("THEME:"):
            theme_text = line.split(":", 1)[1].strip()
            parts = [p.strip().lower() for p in theme_text.split("|")]
            themes.extend(parts)
    return themes


def _match_tags(themes: list[str], seed: list[dict], category: str | None = None) -> list[dict]:
    """Match themes to seed hashtags by keyword overlap."""
    matched = []
    theme_words = set()
    for t in themes:
        theme_words.update(t.lower().split())

    for tag_entry in seed:
        if category and tag_entry.get("category") != category:
            continue

        tag = tag_entry["tag"].lower().replace("#", "").replace("_", "")
        tag_cat = tag_entry.get("category", "").lower()

        # Score by word overlap
        score = 0
        for word in theme_words:
            if word in tag or word in tag_cat:
                score += 1
            if len(word) > 4 and word[:4] in tag:
                score += 0.5

        if score > 0:
            matched.append({**tag_entry, "_score": score})

    matched.sort(key=lambda x: x["_score"], reverse=True)
    return matched


def _apply_mix_strategy(
    matched: list[dict],
    seed: list[dict],
    count: int = 12,
) -> list[dict]:
    """Apply 30/40/30 mix strategy (high/medium/niche)."""
    high_count = max(1, round(count * 0.3))
    medium_count = max(1, round(count * 0.4))
    niche_count = count - high_count - medium_count

    by_tier = {"high": [], "medium": [], "niche": []}
    seen_tags = set()

    # First fill from matched
    for tag in matched:
        tier = tag.get("tier", "medium")
        if tier in by_tier and tag["tag"] not in seen_tags:
            by_tier[tier].append(tag)
            seen_tags.add(tag["tag"])

    # Fill remaining from seed (random from same categories)
    matched_categories = {t.get("category") for t in matched if t.get("category")}
    if matched_categories:
        category_pool = [t for t in seed if t.get("category") in matched_categories and t["tag"] not in seen_tags]
        random.shuffle(category_pool)
        for tag in category_pool:
            tier = tag.get("tier", "medium")
            if tier in by_tier:
                by_tier[tier].append(tag)
                seen_tags.add(tag["tag"])

    result = []
    result.extend(by_tier["high"][:high_count])
    result.extend(by_tier["medium"][:medium_count])
    result.extend(by_tier["niche"][:niche_count])

    return result[:count]


def recommend_hashtags_sync(
    text: str,
    platform: str = "instagram",
    count: int = 12,
) -> dict:
    """Recommend hashtags for the given post text.

    Returns dict with keys: hashtags, mix, themes.
    """
    seed = _load_seed()
    if not seed:
        return {"hashtags": [], "mix": {}, "themes": []}

    themes = _extract_themes_sync(text, platform)

    matched = _match_tags(themes, seed)
    result_tags = _apply_mix_strategy(matched, seed, count=count)

    hashtags = []
    mix = {"high": 0, "medium": 0, "niche": 0}
    for tag in result_tags:
        tier = tag.get("tier", "medium")
        mix[tier] = mix.get(tier, 0) + 1
        hashtags.append({
            "tag": tag["tag"],
            "category": tag.get("category", ""),
            "tier": tier,
            "estimated_posts": tag.get("estimated_posts", 0),
        })

    return {
        "hashtags": hashtags,
        "mix": mix,
        "themes": themes,
    }


def get_library(category: str | None = None, tier: str | None = None) -> list[dict]:
    """Get hashtag library, optionally filtered."""
    seed = _load_seed()
    result = seed
    if category:
        result = [t for t in result if t.get("category") == category]
    if tier:
        result = [t for t in result if t.get("tier") == tier]
    return result
