"""RAG (Retrieval-Augmented Generation) API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from ..auth import _require_auth, require_tier

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/rag/search", dependencies=[Depends(_require_auth)])
async def rag_search(
    q: str = Query(..., min_length=2, max_length=500, description="Search query"),
    top_k: int = Query(5, ge=1, le=20),
    categories: str = Query("", description="Comma-separated: aroma,blend,symptom,practice,sound,concept"),
):
    """Semantic search over the knowledge base."""
    from bot.services.rag import retrieve_relevant_cards

    cat_filter = None
    if categories.strip():
        cat_filter = tuple(c.strip() for c in categories.split(",") if c.strip())

    results = await retrieve_relevant_cards(q, categories=cat_filter, max_items=top_k)
    return {"results": results, "query": q}


@router.get("/api/rag/status", dependencies=[Depends(_require_auth)])
async def rag_status():
    """Check RAG index status."""
    from bot.services.rag.indexer import INDEX_PATH, METADATA_PATH

    if not INDEX_PATH.exists() or not METADATA_PATH.exists():
        return {"ready": False, "indexed": 0}

    import json

    metadata = json.loads(METADATA_PATH.read_text())
    return {
        "ready": True,
        "indexed": metadata.get("indexed_count", 0),
        "model": metadata.get("embedding_model", ""),
        "rebuilt_at": metadata.get("rebuilt_at", ""),
    }


@router.post("/api/rag/rebuild", dependencies=[Depends(require_tier("expert"))])
async def rag_rebuild():
    """Force rebuild of the RAG index."""
    from bot.services.rag.indexer import rebuild_index
    from bot.services.rag.retriever import invalidate_cache

    result = await rebuild_index()
    invalidate_cache()
    return result
