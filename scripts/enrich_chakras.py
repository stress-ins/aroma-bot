"""Enrich aroma cards with chakra associations using Claude Haiku.

For each aroma card missing chakras, sends therapeutic/psychological properties
to Claude and gets back a list of associated chakras.

Usage:
    .venv/bin/python scripts/enrich_chakras.py [--dry-run] [--force] [--slug SLUG]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BATCH_SIZE = 8
BATCH_DELAY = 1.5

CHAKRA_NAMES = [
    "Муладхара (корневая)",
    "Свадхистана (сакральная)",
    "Манипура (солнечного сплетения)",
    "Анахата (сердечная)",
    "Вишуддха (горловая)",
    "Аджна (третьего глаза)",
    "Сахасрара (коронная)",
]

PROMPT_TEMPLATE = """\
Ты — эксперт по ароматерапии и энергетическим практикам.
Для каждого эфирного масла определи, с какими чакрами оно связано.

Масла для обработки:
{items}

Допустимые чакры (используй ТОЧНО эти названия):
{chakra_list}

Правила:
- Обычно масло связано с 1-3 чакрами, редко больше
- Основывайся на терапевтических и психологических свойствах
- Если не уверен — лучше указать меньше, но точнее

Ответь СТРОГО в формате JSON. Ключ — slug, значение — список чакр.
Пример:
{{
  "lavender": ["Анахата (сердечная)", "Аджна (третьего глаза)"],
  "peppermint": ["Манипура (солнечного сплетения)", "Вишуддха (горловая)"]
}}

Никаких пояснений, только JSON.
"""


def enrich_batch(items: list[dict], api_key: str) -> dict[str, list[str]]:
    """Send a batch of aroma cards to Claude Haiku. Return {slug: [chakras]}."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    items_text = "\n".join(
        f"  {item['slug']}: {item['name']}\n"
        f"    therapeutic_properties: {item.get('therapeutic') or '(нет данных)'}\n"
        f"    psychological_properties: {item.get('psychological') or '(нет данных)'}\n"
        f"    description: {item.get('description') or '(нет данных)'}"
        for item in items
    )

    prompt = PROMPT_TEMPLATE.format(
        items=items_text,
        chakra_list="\n".join(f"- {c}" for c in CHAKRA_NAMES),
    )

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


async def run(dry_run: bool = False, force: bool = False, slug: str | None = None) -> None:
    from config import settings
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    api_key = settings.anthropic_api_key
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        all_models = result.scalars().all()

    print(f"Loaded {len(all_models)} aroma cards.")

    if slug:
        candidates = [m for m in all_models if m.slug == slug]
        if not candidates:
            print(f"ERROR: no aroma card found with slug={slug!r}")
            return
    else:
        candidates = all_models

    work_items: list[dict] = []
    for m in candidates:
        payload = m.payload or {}
        has_chakras = bool(payload.get("chakras"))

        if not force and has_chakras:
            continue

        work_items.append({
            "slug": m.slug,
            "name": payload.get("name_ru") or payload.get("name") or m.name or m.slug,
            "therapeutic": str(payload.get("therapeutic_properties") or "")[:500],
            "psychological": str(payload.get("psychological_properties") or "")[:500],
            "description": str(payload.get("description") or "")[:300],
        })

    print(f"Cards to process: {len(work_items)}")
    if not work_items:
        print("Nothing to do.")
        return

    if dry_run:
        for item in work_items[:10]:
            print(f"  Would enrich: {item['slug']} ({item['name']})")
        if len(work_items) > 10:
            print(f"  ... and {len(work_items) - 10} more")
        return

    all_results: dict[str, list[str]] = {}
    for i in range(0, len(work_items), BATCH_SIZE):
        batch = work_items[i: i + BATCH_SIZE]
        print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} cards → Claude Haiku...")
        try:
            batch_result = await asyncio.to_thread(enrich_batch, batch, api_key)
            all_results.update(batch_result)
            print(f"    Got results for {len(batch_result)} cards.")
        except Exception as e:
            print(f"    ERROR in batch: {e}")
        if i + BATCH_SIZE < len(work_items):
            time.sleep(BATCH_DELAY)

    # Validate chakra names
    valid_set = set(CHAKRA_NAMES)
    for card_slug, chakras in all_results.items():
        filtered = [c for c in chakras if c in valid_set]
        if len(filtered) != len(chakras):
            invalid = [c for c in chakras if c not in valid_set]
            print(f"  WARNING: {card_slug} had invalid chakras removed: {invalid}")
        all_results[card_slug] = filtered

    # Write to DB
    updated = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        db_models = result.scalars().all()
        model_map = {m.slug: m for m in db_models}

        for item in work_items:
            card_slug = item["slug"]
            chakras = all_results.get(card_slug)
            if not chakras:
                print(f"  WARNING: no result for {card_slug}")
                continue

            m = model_map.get(card_slug)
            if not m:
                continue

            payload = dict(m.payload or {})
            if not force and payload.get("chakras"):
                continue

            payload["chakras"] = chakras
            m.payload = payload
            updated += 1
            print(f"  Updated: {card_slug} → {chakras}")

        await session.commit()

    print(f"\nDone. Updated {updated} cards with chakra data.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich aroma cards with chakra associations via Claude Haiku")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing")
    parser.add_argument("--force", action="store_true", help="Re-enrich cards that already have chakras")
    parser.add_argument("--slug", type=str, default=None, help="Process only a specific card slug")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, force=args.force, slug=args.slug))
