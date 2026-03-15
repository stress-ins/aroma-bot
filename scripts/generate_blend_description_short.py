#!/usr/bin/env python3
"""Generate description_short for blend cards using Claude haiku.

Usage:
    .venv/bin/python scripts/generate_blend_description_short.py --dry-run
    .venv/bin/python scripts/generate_blend_description_short.py
    .venv/bin/python scripts/generate_blend_description_short.py --limit 20
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROMPT = (
    "Сократи описание ароматической смеси до 1-2 коротких предложений. "
    "Сохрани ключевое назначение смеси и основной эмоциональный эффект. "
    "Не добавляй информацию, которой нет в оригинале. "
    "Не начинай с названия смеси. Ответь только текстом саммари."
)

PROMPT_FROM_NAME = (
    "Напиши краткое описание (1-2 предложения) для ароматической смеси с указанным названием и составом. "
    "Опиши её назначение и основной эффект в контексте ароматерапии. "
    "Не давай медицинских рекомендаций. Ответь только текстом описания."
)


def generate_short(payload: dict[str, Any], name: str, client: Any) -> Optional[str]:
    description = str(payload.get("description", "")).strip()

    if description and len(description) >= 30:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": f"{PROMPT}\n\nОписание: {description}",
            }],
        )
    else:
        # No description — generate from name + ingredients
        ingredients = payload.get("ingredient_names") or []
        ing_ctx = f" Состав: {', '.join(ingredients[:6])}." if ingredients else ""
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": f"{PROMPT_FROM_NAME}\n\nНазвание: {name}{ing_ctx}",
            }],
        )

    return response.content[0].text.strip()


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
            select(AromaCardModel).where(AromaCardModel.category == "blend")
        )
        cards = result.scalars().all()

        updated = 0
        skipped = 0

        for card in cards:
            if limit and updated >= limit:
                break

            payload = dict(card.payload or {})

            if payload.get("description_short"):
                skipped += 1
                continue

            desc_preview = str(payload.get("description", ""))[:60] or card.name
            print(f"  {card.slug}: '{desc_preview}...'")

            if dry_run:
                print(f"    → [dry run] would generate summary")
                updated += 1
                continue

            try:
                summary = generate_short(payload, card.name, client)
                print(f"    → {summary[:80]}")

                payload["description_short"] = summary
                card.payload = payload
                card.updated_at = datetime.now(timezone.utc)
                updated += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"    ERROR: {e}")

        if not dry_run:
            await session.commit()

        print(f"\nDone: {updated} updated, {skipped} already had description_short")
        if dry_run:
            print("[DRY RUN]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate description_short for blends")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max blends to process (0=all)")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
