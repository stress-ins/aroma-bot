"""Embedding model management for RAG.

Uses sentence-transformers with a multilingual model that supports
both Russian and English text — essential for our bilingual knowledge base.

The model is loaded lazily on first use and cached in memory.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

_model: SentenceTransformer | None = None
_lock = threading.Lock()


def _get_model() -> SentenceTransformer:
    """Load embedding model lazily (thread-safe)."""
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s ...", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model loaded (dim=%d)", EMBEDDING_DIM)
        return _model


def encode_texts(texts: list[str]) -> np.ndarray:
    """Encode list of texts into normalized embeddings.

    Returns np.ndarray of shape (len(texts), EMBEDDING_DIM) with float32.
    Vectors are L2-normalized for cosine similarity via dot product.
    """
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(embeddings, dtype=np.float32)


def encode_query(query: str) -> np.ndarray:
    """Encode a single query string. Returns shape (EMBEDDING_DIM,)."""
    return encode_texts([query])[0]
