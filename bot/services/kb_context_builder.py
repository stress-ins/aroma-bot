"""KBContextBuilder — builds structured KB context for content generation agents."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


@dataclass
class KBContext:
    cards: list[dict[str, Any]] = field(default_factory=list)
    topic: str = ""
    platform: str = ""

    def as_prompt_text(self) -> str:
        """Format KB context as a compact text block for Claude prompts."""
        if not self.cards:
            return ""
        lines = ["Релевантные материалы из базы знаний:"]
        for card in self.cards:
            name = card.get("name", "")
            category = card.get("category", "")
            description = card.get("description", "")
            props = card.get("therapeutic_properties", "")
            psych = card.get("psychological_properties", "")

            line = f"- [{category}] {name}"
            if description:
                line += f": {description[:120]}"
            if props:
                line += f" | Свойства: {str(props)[:80]}"
            if psych:
                line += f" | Психо: {str(psych)[:80]}"
            lines.append(line)
        return "\n".join(lines)


def _card_matches(card: AromaCardModel, keywords: list[str]) -> bool:
    """Simple keyword matching against card name, aliases, and payload text."""
    searchable = " ".join(filter(None, [
        card.name or "",
        " ".join(card.aliases or []),
        str(card.payload.get("description", "")),
        str(card.payload.get("therapeutic_properties", "")),
        str(card.payload.get("psychological_properties", "")),
        " ".join(card.payload.get("usage_contexts", [])),
    ])).lower()

    return any(kw.lower() in searchable for kw in keywords)


def _extract_keywords(topic: str) -> list[str]:
    """Extract meaningful keywords from topic string."""
    stop_words = {
        "и", "в", "на", "с", "для", "к", "по", "при", "о", "от", "из",
        "что", "как", "это", "а", "но", "или", "не", "то",
    }
    words = [w.strip(".,!?:;\"'") for w in topic.lower().split()]
    return [w for w in words if w and w not in stop_words and len(w) > 2]


async def build_content_context(
    topic: str,
    platform: str = "",
    max_cards: int = 5,
    categories: list[str] | None = None,
) -> KBContext:
    """
    Fetch relevant AromaCards by keyword matching against topic.
    Returns KBContext with matched cards formatted for Claude prompts.
    """
    keywords = _extract_keywords(topic)
    if not keywords:
        return KBContext(topic=topic, platform=platform)

    target_categories = set(categories) if categories else {"aroma", "practice", "sound", "blend"}

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(
                AromaCardModel.category.in_(target_categories)
            ).limit(300)
        )
        all_cards = result.scalars().all()

    matched: list[dict[str, Any]] = []
    for card in all_cards:
        if _card_matches(card, keywords):
            payload = card.payload or {}
            matched.append({
                "slug": card.slug,
                "name": card.name,
                "category": card.category,
                "description": payload.get("description", ""),
                "therapeutic_properties": payload.get("therapeutic_properties", ""),
                "psychological_properties": payload.get("psychological_properties", ""),
                "usage_contexts": payload.get("usage_contexts", []),
                "complementary_oil_slugs": payload.get("complementary_oil_slugs", []),
            })
        if len(matched) >= max_cards:
            break

    # If no matches, fall back to top aroma cards by recency
    if not matched:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AromaCardModel)
                .where(AromaCardModel.category == "aroma")
                .order_by(AromaCardModel.updated_at.desc())
                .limit(max_cards)
            )
            fallback_cards = result.scalars().all()
        for card in fallback_cards:
            payload = card.payload or {}
            matched.append({
                "slug": card.slug,
                "name": card.name,
                "category": card.category,
                "description": payload.get("description", ""),
                "therapeutic_properties": payload.get("therapeutic_properties", ""),
                "psychological_properties": payload.get("psychological_properties", ""),
                "usage_contexts": [],
                "complementary_oil_slugs": [],
            })

    logger.debug("KBContextBuilder: topic=%r keywords=%r matched=%d", topic, keywords, len(matched))
    return KBContext(cards=matched[:max_cards], topic=topic, platform=platform)
