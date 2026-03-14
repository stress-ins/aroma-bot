#!/usr/bin/env python3
"""Enrich cards where description is shorter than --min-length characters.

Usage:
    .venv/bin/python scripts/enrich_short_descriptions.py [--dry-run] [--min-length 60] [--category aroma]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BATCH_SIZE = 10
BATCH_DELAY = 2.0

ENRICH_PROMPT = """\
Ты — эксперт по ароматерапии. Для каждой карточки напиши развёрнутое описание: 3–5 предложений.
Упомяни ключевые свойства, применение, эмоциональное и терапевтическое воздействие.
Пиши по-русски, связным текстом, без маркированных списков.

Ответь СТРОГО в формате JSON: объект, где ключ = slug карточки, значение = текст описания.
Никаких пояснений, только JSON.

Карточки для обработки:
{items}
"""


def _enrich_batch(items: list[dict], api_key: str) -> dict[str, str]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    items_text = "\n".join(
        f'- slug "{item["slug"]}", название "{item["name"]}", текущее описание: "{item["description"][:200]}"'
        for item in items
    )
    prompt = ENRICH_PROMPT.format(items=items_text)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
    raw = raw.rstrip("`").strip()
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        raw = json_match.group(0)
    return json.loads(raw)


async def run(dry_run: bool, min_length: int, category: str) -> None:
    from config import settings
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select
    from datetime import datetime, timezone

    api_key = settings.anthropic_api_key
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == category)
        )
        models = result.scalars().all()

    work_items = []
    for m in models:
        payload = m.payload or {}
        desc = str(payload.get("description", "") or "").strip()
        if len(desc) < min_length:
            work_items.append({
                "slug": m.slug,
                "name": str(payload.get("name_ru") or payload.get("name") or m.name),
                "description": desc,
            })

    print(f"Cards with description < {min_length} chars: {len(work_items)}")
    if not work_items:
        print("Nothing to do.")
        return

    if dry_run:
        for item in work_items[:10]:
            print(f"  Would enrich: {item['slug']} ({len(item['description'])} chars)")
        if len(work_items) > 10:
            print(f"  ... and {len(work_items) - 10} more")
        return

    all_results: dict[str, str] = {}
    for i in range(0, len(work_items), BATCH_SIZE):
        batch = work_items[i: i + BATCH_SIZE]
        print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} items → Claude Haiku...")
        try:
            result_map = await asyncio.to_thread(_enrich_batch, batch, api_key)
            all_results.update(result_map)
            print(f"    Got {len(result_map)} descriptions.")
        except Exception as e:
            print(f"    ERROR in batch: {e}")
        if i + BATCH_SIZE < len(work_items):
            await asyncio.sleep(BATCH_DELAY)

    updated = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == category)
        )
        db_models = result.scalars().all()
        model_map = {m.slug: m for m in db_models}
        for slug, new_desc in all_results.items():
            new_desc = new_desc.strip()
            if not new_desc or len(new_desc) < min_length:
                continue
            m = model_map.get(slug)
            if not m:
                continue
            new_payload = dict(m.payload or {})
            new_payload["description"] = new_desc
            m.payload = new_payload
            m.updated_at = datetime.now(timezone.utc)
            updated += 1
        await session.commit()

    print(f"\nDone: {updated} cards updated with enriched descriptions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich short card descriptions via Claude")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    parser.add_argument("--min-length", type=int, default=60, help="Minimum description length")
    parser.add_argument("--category", default="aroma", help="Card category (aroma, blend, symptom, ...)")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, min_length=args.min_length, category=args.category))
