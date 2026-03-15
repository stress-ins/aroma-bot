#!/usr/bin/env python3
"""Phase 4: Generate short descriptions for symptoms that lack them.

Usage:
    .venv/bin/python scripts/generate_symptom_descriptions.py --dry-run
    .venv/bin/python scripts/generate_symptom_descriptions.py
    .venv/bin/python scripts/generate_symptom_descriptions.py --limit 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROMPT = (
    "Напиши краткое описание (1-2 предложения) для следующего симптома/состояния "
    "в контексте ароматерапии. Не давай медицинских рекомендаций и диагнозов. "
    "Опиши, что это за состояние и как ароматерапия может помочь в комплексном подходе. "
    "Ответь только текстом описания."
)


async def run(dry_run: bool = False, limit: int = 0) -> None:
    import anthropic
    from sqlalchemy import select
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from config import settings

    if not settings.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "symptom")
        )
        cards = result.scalars().all()

        updated = 0
        skipped = 0

        for card in cards:
            if limit and updated >= limit:
                break

            payload = dict(card.payload or {})
            desc = str(payload.get("description", "")).strip()
            if desc and len(desc) >= 20:
                skipped += 1
                continue

            name = card.name
            print(f"  {card.slug}: '{name}'")

            if dry_run:
                print(f"    → [dry run]")
                updated += 1
                continue

            try:
                # Include recommended oils for context
                oils = payload.get("recommended_oil_names") or []
                oil_ctx = f" Рекомендуемые масла: {', '.join(oils[:5])}." if oils else ""

                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=200,
                    messages=[{
                        "role": "user",
                        "content": f"{PROMPT}\n\nСимптом: {name}{oil_ctx}",
                    }],
                )
                summary = response.content[0].text.strip()
                print(f"    → {summary[:80]}")

                payload["description"] = summary
                card.payload = payload
                card.updated_at = datetime.now(timezone.utc)
                updated += 1
                time.sleep(0.3)
            except Exception as e:
                print(f"    ERROR: {e}")

        if not dry_run:
            await session.commit()

        print(f"\nDone: {updated} updated, {skipped} already had description")
        if dry_run:
            print("[DRY RUN]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max symptoms to process (0=all)")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
