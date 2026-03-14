#!/usr/bin/env python3
"""Generate description_short for aroma cards using Claude haiku.

Usage:
    .venv/bin/python scripts/generate_description_short.py --dry-run   # preview
    .venv/bin/python scripts/generate_description_short.py              # run
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
    "Сократи описание эфирного масла до 1-2 коротких предложений. "
    "Сохрани все ключевые факты и эмоциональный тон. "
    "Не добавляй информацию, которой нет в оригинале. "
    "Не начинай с названия масла. Ответь только текстом саммари."
)


async def run(dry_run: bool = False) -> None:
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
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        cards = result.scalars().all()

        skipped = 0
        updated = 0
        no_desc = 0

        for card in cards:
            payload = dict(card.payload or {})
            description = str(payload.get("description", "")).strip()

            # Skip if already has description_short
            if payload.get("description_short"):
                skipped += 1
                continue

            # Skip if no description to summarize
            if not description or len(description) < 30:
                no_desc += 1
                continue

            print(f"  {card.slug}: '{description[:60]}...'")

            if dry_run:
                print(f"    → [dry run] would generate summary")
                updated += 1
                continue

            try:
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=200,
                    messages=[{
                        "role": "user",
                        "content": f"{PROMPT}\n\nОписание: {description}",
                    }],
                )
                summary = response.content[0].text.strip()
                print(f"    → {summary[:80]}")

                payload["description_short"] = summary
                card.payload = payload
                card.updated_at = datetime.now(timezone.utc)
                updated += 1

                # Rate limiting
                time.sleep(0.5)
            except Exception as e:
                print(f"    ERROR: {e}")

        if not dry_run:
            await session.commit()

        print(f"\nDone: {updated} updated, {skipped} already had summary, {no_desc} no description")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate description_short for aromas")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
