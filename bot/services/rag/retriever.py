"""Semantic retrieval over the Aromara knowledge base.

Queries the FAISS index to find cards/blends most relevant to a given text,
then fetches full data from the database for prompt injection.
"""

from __future__ import annotations

import logging
from typing import Any

from .embeddings import encode_query
from .indexer import load_index, rebuild_index

logger = logging.getLogger(__name__)

_cached_index = None
_cached_docs = None


def _ensure_index() -> tuple:
    """Load or rebuild the index."""
    global _cached_index, _cached_docs
    if _cached_index is not None and _cached_docs is not None:
        return _cached_index, _cached_docs

    result = load_index()
    if result is None:
        return None, None

    _cached_index, _cached_docs = result
    return _cached_index, _cached_docs


def invalidate_cache() -> None:
    """Clear the in-memory index cache (e.g. after rebuild)."""
    global _cached_index, _cached_docs
    _cached_index = None
    _cached_docs = None


async def retrieve_relevant_cards(
    query: str,
    *,
    categories: tuple[str, ...] | None = None,
    max_items: int = 5,
    similarity_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Retrieve reference cards semantically relevant to the query.

    Args:
        query: Search text (topic, question, keywords).
        categories: Filter by card categories (e.g. ("aroma", "blend")).
                    None means all categories.
        max_items: Maximum number of results.
        similarity_threshold: Minimum cosine similarity score (0-1).

    Returns:
        List of dicts with keys: slug, name, name_ru, category, type, score, snippet.
    """
    index, docs = _ensure_index()
    if index is None or docs is None:
        logger.warning("RAG index not available, trying to rebuild ...")
        try:
            await rebuild_index()
            invalidate_cache()
            index, docs = _ensure_index()
        except Exception:
            logger.error("Failed to rebuild RAG index", exc_info=True)
            return []

    if index is None:
        return []

    query_vec = encode_query(query).reshape(1, -1)

    # Search more than needed, then filter by category
    search_k = min(max_items * 3, index.ntotal)
    scores, indices = index.search(query_vec, search_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(docs):
            continue
        if score < similarity_threshold:
            continue

        doc = docs[idx]
        if categories and doc["category"] not in categories:
            continue

        results.append({
            "slug": doc["slug"],
            "name": doc["name"],
            "name_ru": doc.get("name_ru", ""),
            "category": doc["category"],
            "source_type": doc.get("source_type", ""),
            "type": doc["type"],
            "score": round(float(score), 3),
        })

        if len(results) >= max_items:
            break

    return results


async def retrieve_with_full_data(
    query: str,
    *,
    categories: tuple[str, ...] | None = None,
    max_items: int = 5,
    similarity_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Retrieve cards with full payload data from DB (for prompt injection)."""
    from sqlalchemy import select

    from db.models import AromaCardModel, BlendModel
    from db.session import AsyncSessionLocal

    basic_results = await retrieve_relevant_cards(
        query, categories=categories, max_items=max_items,
        similarity_threshold=similarity_threshold,
    )
    if not basic_results:
        return []

    card_slugs = [r["slug"] for r in basic_results if r["type"] == "card"]
    blend_slugs = [r["slug"] for r in basic_results if r["type"] == "blend"]

    cards_by_slug = {}
    blends_by_slug = {}

    async with AsyncSessionLocal() as session:
        if card_slugs:
            stmt = select(AromaCardModel).where(AromaCardModel.slug.in_(card_slugs))
            rows = await session.execute(stmt)
            for row in rows.scalars():
                payload = row.payload or {}
                cards_by_slug[row.slug] = {
                    "slug": row.slug,
                    "name": row.name,
                    "name_ru": payload.get("name_ru", ""),
                    "category": row.category,
                    "source_type": row.source_type or "",
                    "description_short": payload.get("description_short", ""),
                    "therapeutic_properties": payload.get("therapeutic_properties", ""),
                    "psychological_properties": payload.get("psychological_properties", ""),
                    "applications": payload.get("applications", ""),
                    "health_effects": payload.get("health_effects", ""),
                    "contraindications": payload.get("conditions_for_use", ""),
                }

        if blend_slugs:
            stmt = select(BlendModel).where(BlendModel.slug.in_(blend_slugs))
            rows = await session.execute(stmt)
            for row in rows.scalars():
                ingredients = row.ingredients or []
                oil_names = [i.get("name", "") for i in ingredients if isinstance(i, dict)]
                blends_by_slug[row.slug] = {
                    "slug": row.slug,
                    "name": row.name,
                    "goal": row.goal or "",
                    "oils": ", ".join(oil_names),
                    "indications": row.indications or "",
                    "contraindications": row.contraindications or "",
                }

    enriched = []
    for r in basic_results:
        if r["type"] == "card" and r["slug"] in cards_by_slug:
            data = cards_by_slug[r["slug"]]
            data["score"] = r["score"]
            data["type"] = "card"
            enriched.append(data)
        elif r["type"] == "blend" and r["slug"] in blends_by_slug:
            data = blends_by_slug[r["slug"]]
            data["score"] = r["score"]
            data["type"] = "blend"
            data["category"] = "blend"
            enriched.append(data)

    return enriched


def format_rag_context(cards: list[dict[str, Any]], max_chars: int = 2000) -> str:
    """Format retrieved cards as a context block for prompt injection.

    Returns a string like:
        ## Релевантные данные из базы знаний
        ### Лаванда (aroma, score: 0.92)
        Описание: ...
        Свойства: ...
    """
    if not cards:
        return ""

    lines = ["## Релевантные данные из базы знаний"]
    lines.append("Используй ТОЛЬКО факты из этого раздела. Не добавляй информацию, которой здесь нет.\n")

    total = 0
    for card in cards:
        name = card.get("name_ru") or card.get("name", "")
        category = card.get("category", "")
        score = card.get("score", 0)

        header = f"### {name} ({category}, релевантность: {score})"
        parts = [header]

        if card["type"] == "card":
            if card.get("description_short"):
                parts.append(f"Описание: {card['description_short']}")
            if card.get("therapeutic_properties"):
                val = card["therapeutic_properties"]
                if isinstance(val, list):
                    val = ", ".join(val)
                parts.append(f"Терапевтические свойства: {val}")
            if card.get("psychological_properties"):
                val = card["psychological_properties"]
                if isinstance(val, list):
                    val = ", ".join(val)
                parts.append(f"Психологические свойства: {val}")
            if card.get("applications"):
                val = card["applications"]
                if isinstance(val, list):
                    val = ", ".join(val)
                parts.append(f"Применение: {val}")
            if card.get("health_effects"):
                val = card["health_effects"]
                if isinstance(val, list):
                    val = ", ".join(val)
                parts.append(f"Воздействие на здоровье: {val}")
            if card.get("contraindications"):
                parts.append(f"Противопоказания: {card['contraindications']}")
        elif card["type"] == "blend":
            if card.get("goal"):
                parts.append(f"Цель: {card['goal']}")
            if card.get("oils"):
                parts.append(f"Масла в составе: {card['oils']}")
            if card.get("indications"):
                parts.append(f"Показания: {card['indications']}")
            if card.get("contraindications"):
                parts.append(f"Противопоказания: {card['contraindications']}")

        block = "\n".join(parts) + "\n"
        if total + len(block) > max_chars:
            break
        lines.append(block)
        total += len(block)

    return "\n".join(lines)
