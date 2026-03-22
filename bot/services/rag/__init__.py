"""RAG (Retrieval-Augmented Generation) engine for Aromara knowledge base.

Provides semantic search over essential oils, blends, symptoms, and other
reference cards stored in the aroma_cards and blends tables.
"""

from .retriever import retrieve_relevant_cards, format_rag_context

__all__ = ["retrieve_relevant_cards", "format_rag_context"]
