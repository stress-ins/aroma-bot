"""Generate complementary essential oils for aroma cards using Claude Haiku.

For each aroma card (category=aroma) that lacks complementary_oil_names (or has fewer
than 3), asks Claude Haiku to suggest 3–5 complementary essential oils.
Results are stored in payload as:
  - complementary_oil_names  — list of Russian oil names
  - complementary_oil_slugs  — list of matching slugs from the DB

Claude is given the full list of known slugs+names so it can match by name.

Batch format returned by Claude:
  {"<slug>": {"names": ["name1", ...], "slugs": ["slug1", ...]}, ...}

Usage:
    .venv/bin/python scripts/generate_complementary_oils.py [--dry-run] [--force] [--slug SLUG]
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

BATCH_SIZE = 10  # aroma cards per Claude request
MIN_OILS = 3     # skip cards that already have this many or more

PROMPT_TEMPLATE = """\
Ты — эксперт-ароматерапевт. Тебе дан список эфирных масел (карточек ароматерапии).
Для каждого масла предложи 3–5 комплементарных эфирных масел, которые хорошо сочетаются с ним \
по аромату и терапевтическому эффекту.

Выбирай названия ТОЛЬКО из предоставленного справочника масел (список ниже).
Если подходящего масла нет в справочнике — пропусти его.
Возвращай русские названия и соответствующие slugs из справочника.

Справочник доступных масел (slug → русское название):
{known_oils}

Масла для обработки (slug → название и описание):
{items}

Ответь СТРОГО в формате JSON. Ключ — slug обрабатываемого масла, значение — объект с полями:
  "names": список русских названий комплементарных масел (из справочника)
  "slugs": список соответствующих slugs (из справочника)

Пример:
{{
  "lavender": {{"names": ["Ромашка римская", "Бергамот"], "slugs": ["roman-chamomile", "bergamot"]}},
  "peppermint": {{"names": ["Эвкалипт", "Лимон"], "slugs": ["eucalyptus", "lemon"]}}
}}

Никаких пояснений, только JSON.
"""


def generate_batch(
    items: list[dict],
    known_oils: dict[str, str],
    api_key: str,
) -> dict[str, dict]:
    """Send a batch of aroma cards to Claude Haiku. Return {slug: {names, slugs}}."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    known_oils_text = "\n".join(
        f"  {slug}: {name}" for slug, name in sorted(known_oils.items())
    )
    items_text = "\n".join(
        f"  {item['slug']}: {item['name']} — {item['description'][:300]}"
        for item in items
    )

    prompt = PROMPT_TEMPLATE.format(
        known_oils=known_oils_text,
        items=items_text,
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
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
    from datetime import datetime, timezone

    api_key = settings.anthropic_api_key
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        all_models = result.scalars().all()

    print(f"Loaded {len(all_models)} aroma cards.")

    # Build the known-oils lookup: slug → name (from all aroma cards)
    known_oils: dict[str, str] = {}
    for m in all_models:
        name = (m.payload or {}).get("name") or m.name or ""
        if name:
            known_oils[m.slug] = name

    # Filter to cards that need processing
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
        existing = payload.get("complementary_oil_names") or []
        if not force and len(existing) >= MIN_OILS:
            continue  # already has enough

        name = payload.get("name") or m.name or m.slug
        description = (
            payload.get("description")
            or payload.get("short_description")
            or payload.get("therapeutic_properties")
            or ""
        )
        work_items.append({
            "slug": m.slug,
            "name": name,
            "description": str(description).strip(),
        })

    print(f"Cards to process: {len(work_items)}")
    if not work_items:
        print("Nothing to do.")
        return

    if dry_run:
        for item in work_items[:10]:
            print(f"  Would generate for: {item['slug']} ({item['name']})")
        if len(work_items) > 10:
            print(f"  ... and {len(work_items) - 10} more")
        return

    # Process in batches
    all_results: dict[str, dict] = {}
    for i in range(0, len(work_items), BATCH_SIZE):
        batch = work_items[i : i + BATCH_SIZE]
        print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} cards → Claude Haiku...")
        try:
            batch_result = await asyncio.to_thread(
                generate_batch, batch, known_oils, api_key
            )
            all_results.update(batch_result)
            print(f"    Got results for {len(batch_result)} cards.")
        except Exception as e:
            print(f"    ERROR in batch: {e}")

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
            oil_data = all_results.get(card_slug)
            if not oil_data:
                print(f"  WARNING: no result for {card_slug}")
                continue

            names = oil_data.get("names") or []
            slugs = oil_data.get("slugs") or []

            if not names:
                print(f"  WARNING: empty names for {card_slug}")
                continue

            # Validate that returned slugs exist in known_oils
            valid_pairs = [
                (n, s) for n, s in zip(names, slugs) if s in known_oils
            ]
            if not valid_pairs:
                print(f"  WARNING: no valid slug matches for {card_slug}")
                continue

            valid_names = [p[0] for p in valid_pairs]
            valid_slugs = [p[1] for p in valid_pairs]

            m = model_map.get(card_slug)
            if not m:
                continue

            new_payload = dict(m.payload or {})
            new_payload["complementary_oil_names"] = valid_names
            new_payload["complementary_oil_slugs"] = valid_slugs
            m.payload = new_payload
            m.updated_at = datetime.now(timezone.utc)
            updated += 1
            print(f"  {card_slug}: {valid_names}")

        await session.commit()

    print(f"\nDone: {updated} cards updated with complementary oils.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate complementary oils for aroma cards via Claude Haiku"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to DB",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-generate even if complementary_oil_names already exists",
    )
    parser.add_argument(
        "--slug",
        metavar="SLUG",
        help="Process only the aroma card with this slug",
    )
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, force=args.force, slug=args.slug))


if __name__ == "__main__":
    main()
