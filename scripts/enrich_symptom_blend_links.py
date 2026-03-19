"""Enrich symptom cards with recommended blend links using Claude Haiku.

For each symptom card missing recommended_blend_slugs, sends the symptom
description plus all available blends to Claude and gets back matching blends.

Usage:
    .venv/bin/python scripts/enrich_symptom_blend_links.py [--dry-run] [--force] [--slug SLUG]
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

BATCH_SIZE = 10
BATCH_DELAY = 1.5

PROMPT_TEMPLATE = """\
Ты — эксперт-ароматерапевт. Тебе даны симптомы/состояния и список доступных блендов эфирных масел.
Для каждого симптома подбери подходящие бленды (от 2 до 7).

Симптомы для обработки:
{items}

Доступные бленды (slug: название — показания):
{blend_list}

Правила:
- Выбирай бленды, которые РЕАЛЬНО помогают при данном симптоме/состоянии
- Основывайся на показаниях (indications) и цели (goal) бленда
- Лучше меньше, но точнее — не добавляй сомнительные связи
- Минимум 2, максимум 7 блендов на симптом

Ответь СТРОГО в формате JSON. Ключ — slug симптома, значение — список slug'ов блендов.
Пример:
{{
  "headache": ["relaxing-blend", "anti-stress-blend"],
  "insomnia": ["sleep-blend", "calming-blend", "lavender-chamomile"]
}}

Никаких пояснений, только JSON.
"""


def enrich_batch(
    items: list[dict], blend_list_str: str, api_key: str
) -> dict[str, list[str]]:
    """Send a batch of symptoms to Claude Haiku. Return {symptom_slug: [blend_slugs]}."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    items_text = "\n".join(
        f"  {item['slug']}: {item['name']}\n"
        f"    description: {item.get('description') or '(нет описания)'}\n"
        f"    recommended_oils: {item.get('oils_hint') or '(нет данных)'}"
        for item in items
    )

    prompt = PROMPT_TEMPLATE.format(
        items=items_text,
        blend_list=blend_list_str,
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
    from db.models import AromaCardModel, BlendModel
    from sqlalchemy import select
    from datetime import datetime, timezone

    api_key = settings.anthropic_api_key
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    # Load blends
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BlendModel))
        all_blends = result.scalars().all()

    blend_map = {b.slug: b for b in all_blends}
    print(f"Loaded {len(all_blends)} blends.")

    if not all_blends:
        print("ERROR: no blends in DB — nothing to link.")
        return

    # Build blend list for prompt
    blend_list_str = "\n".join(
        f"  {b.slug}: {b.name} — {(b.indications or b.goal or '')[:200]}"
        for b in sorted(all_blends, key=lambda x: x.name or "")
    )

    # Load symptom cards
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "symptom")
        )
        all_symptoms = result.scalars().all()

    print(f"Loaded {len(all_symptoms)} symptom cards.")

    if slug:
        candidates = [m for m in all_symptoms if m.slug == slug]
        if not candidates:
            print(f"ERROR: no symptom card found with slug={slug!r}")
            return
    else:
        candidates = all_symptoms

    work_items: list[dict] = []
    for m in candidates:
        payload = m.payload or {}
        has_blends = bool(payload.get("recommended_blend_slugs"))

        if not force and has_blends:
            continue

        oil_names = payload.get("recommended_oil_names") or []
        work_items.append({
            "slug": m.slug,
            "name": payload.get("name_ru") or payload.get("name") or m.name or m.slug,
            "description": str(payload.get("description") or "")[:400],
            "oils_hint": ", ".join(oil_names[:8]) if oil_names else "",
        })

    print(f"Symptoms to process: {len(work_items)}")
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
        print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} symptoms → Claude Haiku...")
        try:
            batch_result = await asyncio.to_thread(
                enrich_batch, batch, blend_list_str, api_key
            )
            all_results.update(batch_result)
            print(f"    Got results for {len(batch_result)} symptoms.")
        except Exception as e:
            print(f"    ERROR in batch: {e}")
        if i + BATCH_SIZE < len(work_items):
            time.sleep(BATCH_DELAY)

    # Validate blend slugs exist
    for sym_slug, blend_slugs in list(all_results.items()):
        valid = [s for s in blend_slugs if s in blend_map]
        if len(valid) != len(blend_slugs):
            invalid = [s for s in blend_slugs if s not in blend_map]
            print(f"  WARNING: {sym_slug} had invalid blend slugs removed: {invalid}")
        all_results[sym_slug] = valid

    # Write to DB
    updated = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "symptom")
        )
        db_models = result.scalars().all()
        model_map = {m.slug: m for m in db_models}

        for item in work_items:
            sym_slug = item["slug"]
            blend_slugs = all_results.get(sym_slug)
            if not blend_slugs:
                print(f"  WARNING: no result for {sym_slug}")
                continue

            m = model_map.get(sym_slug)
            if not m:
                continue

            payload = dict(m.payload or {})
            if not force and payload.get("recommended_blend_slugs"):
                continue

            # Build name list from slugs
            blend_names = [blend_map[s].name for s in blend_slugs if s in blend_map]

            payload["recommended_blend_slugs"] = blend_slugs
            payload["recommended_blend_names"] = blend_names
            m.payload = payload
            m.updated_at = datetime.now(timezone.utc)
            updated += 1
            print(f"  Updated: {sym_slug} → {len(blend_slugs)} blends")

        await session.commit()

    print(f"\nDone. Updated {updated} symptom cards with blend links.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enrich symptom cards with recommended blend links via Claude Haiku"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing")
    parser.add_argument("--force", action="store_true", help="Re-enrich symptoms that already have blend links")
    parser.add_argument("--slug", type=str, default=None, help="Process only a specific symptom slug")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, force=args.force, slug=args.slug))
