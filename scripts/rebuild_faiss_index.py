#!/usr/bin/env python3
"""Rebuild the FAISS index for RAG from current database contents.

Usage:
    .venv/bin/python scripts/rebuild_faiss_index.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.services.rag.indexer import rebuild_index


async def main():
    result = await rebuild_index()
    print(f"Index rebuilt: {result['indexed']} documents")
    print(f"Rebuilt at: {result.get('rebuilt_at', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
