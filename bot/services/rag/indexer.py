"""FAISS index builder for the Aromara knowledge base.

Reads all reference cards (aroma, blend, symptom, practice, sound, concept)
from the database, generates embeddings, and builds a FAISS index stored
on disk as `data/rag_index.faiss` + `data/rag_metadata.json`.

The index can be rebuilt on demand via `rebuild_index()` or at app startup.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .embeddings import EMBEDDING_DIM, encode_texts

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parents[3]
INDEX_PATH = _BASE_DIR / "data" / "rag_index.faiss"
METADATA_PATH = _BASE_DIR / "data" / "rag_metadata.json"


def _card_to_text(card: dict) -> str:
    """Build embedding text from card fields."""
    parts = []
    for field in ("name", "name_ru", "name_en"):
        val = card.get(field) or ""
        if val:
            parts.append(val)

    payload = card.get("payload") or {}
    for field in (
        "description", "description_short",
        "therapeutic_properties", "psychological_properties",
        "applications", "key", "history",
        "health_effects", "mind_effect", "spiritual_emotional",
    ):
        val = payload.get(field) or ""
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        if val:
            parts.append(str(val)[:300])

    aliases = card.get("aliases") or []
    if aliases:
        parts.append(", ".join(aliases[:5]))

    source_type = card.get("source_type") or ""
    if source_type:
        parts.append(source_type)

    return " ".join(parts)


def _blend_to_text(blend: dict) -> str:
    """Build embedding text from blend fields."""
    parts = []
    for field in ("name", "goal"):
        val = blend.get(field) or ""
        if val:
            parts.append(val)

    ingredients = blend.get("ingredients") or []
    oil_names = [i.get("name", "") for i in ingredients if isinstance(i, dict)]
    if oil_names:
        parts.append("масла: " + ", ".join(oil_names))

    for field in ("indications", "contraindications"):
        val = blend.get(field) or ""
        if val:
            parts.append(str(val)[:300])

    return " ".join(parts)


async def _load_all_cards() -> list[dict]:
    """Load all reference cards from DB."""
    from sqlalchemy import select

    from db.models import AromaCardModel
    from db.session import AsyncSessionLocal

    items = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel))
        for row in result.scalars():
            items.append({
                "slug": row.slug,
                "name": row.name,
                "name_ru": (row.payload or {}).get("name_ru", ""),
                "name_en": (row.payload or {}).get("name_en", ""),
                "category": row.category,
                "source_type": row.source_type or "",
                "aliases": row.aliases or [],
                "payload": row.payload or {},
                "type": "card",
            })
    return items


async def _load_all_blends() -> list[dict]:
    """Load all blends from DB."""
    from sqlalchemy import select

    from db.models import BlendModel
    from db.session import AsyncSessionLocal

    items = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BlendModel))
        for row in result.scalars():
            items.append({
                "slug": row.slug,
                "name": row.name,
                "goal": row.goal or "",
                "ingredients": row.ingredients or [],
                "indications": row.indications or "",
                "contraindications": row.contraindications or "",
                "type": "blend",
            })
    return items


async def rebuild_index() -> dict:
    """Rebuild the FAISS index from all cards and blends.

    Returns metadata dict with stats.
    """
    import faiss

    logger.info("Rebuilding RAG index ...")

    cards = await _load_all_cards()
    blends = await _load_all_blends()

    documents: list[dict] = []
    texts: list[str] = []

    for card in cards:
        text = _card_to_text(card)
        if text.strip():
            documents.append({
                "id": f"card:{card['category']}:{card['slug']}",
                "slug": card["slug"],
                "category": card["category"],
                "source_type": card.get("source_type", ""),
                "name": card["name"],
                "name_ru": card.get("name_ru", ""),
                "type": "card",
            })
            texts.append(text)

    for blend in blends:
        text = _blend_to_text(blend)
        if text.strip():
            documents.append({
                "id": f"blend:{blend['slug']}",
                "slug": blend["slug"],
                "category": "blend",
                "source_type": "",
                "name": blend["name"],
                "name_ru": "",
                "type": "blend",
            })
            texts.append(text)

    if not texts:
        logger.warning("No documents to index!")
        return {"indexed": 0}

    embeddings = encode_texts(texts)

    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    index.add(embeddings)

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_PATH))

    metadata = {
        "documents": documents,
        "indexed_count": len(documents),
        "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
        "embedding_dim": EMBEDDING_DIM,
        "rebuilt_at": datetime.now(timezone.utc).isoformat(),
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))

    logger.info("RAG index rebuilt: %d documents", len(documents))
    return {"indexed": len(documents), "rebuilt_at": metadata["rebuilt_at"]}


def load_index() -> tuple | None:
    """Load existing FAISS index + metadata from disk.

    Returns (faiss_index, documents_list) or None if not found.
    """
    if not INDEX_PATH.exists() or not METADATA_PATH.exists():
        return None

    import faiss

    index = faiss.read_index(str(INDEX_PATH))
    metadata = json.loads(METADATA_PATH.read_text())
    return index, metadata["documents"]
