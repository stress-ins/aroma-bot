"""Shared helpers for content generation modules — eliminates duplication."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def fetch_rag_context(topic: str, max_items: int = 5) -> str:
    """Retrieve RAG knowledge base context for a topic. Returns empty string on failure."""
    try:
        from bot.services.rag import retrieve_relevant_cards, format_rag_context
        cards = await retrieve_relevant_cards(topic, max_items=max_items)
        return format_rag_context(cards)
    except Exception:
        logger.debug("RAG context retrieval failed for topic=%r", topic, exc_info=True)
        return ""


async def prefetch_stock_photos(keywords: list[str]) -> list[dict]:
    """Search stock photo APIs for given keywords. Returns empty list on failure."""
    if not keywords:
        return []
    try:
        from bot.services.stock_photos import search_stock_photos
        from config import settings
        photos = await search_stock_photos(
            keywords,
            unsplash_key=settings.unsplash_access_key,
            pexels_key=settings.pexels_api_key,
        )
        return photos or []
    except Exception:
        logger.debug("Stock photo prefetch failed for keywords=%r", keywords, exc_info=True)
        return []
