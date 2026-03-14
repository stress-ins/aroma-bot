"""Enrich aroma card passport fields using Claude Haiku.

Fills empty passport fields (botanical_family, origin_countries, extraction_method,
volatility) and short description for aroma cards that lack them.

Also fills description_short (< 100 chars) when description >= 100 chars.

Batch format returned by Claude:
  {"<slug>": {"botanical_family": "...", "origin_countries": "...", ...}, ...}

Usage:
    .venv/bin/python scripts/enrich_passport_fields.py [--dry-run] [--force] [--slug SLUG]
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

BATCH_SIZE = 8  # cards per Claude request
BATCH_DELAY = 1.5  # seconds between batches

PASSPORT_FIELDS = [
    "botanical_family",
    "origin_countries",
    "extraction_method",
    "volatility",
]

PROMPT_TEMPLATE = """\
Ты — эксперт-ароматерапевт. Тебе дан список эфирных масел.
Для каждого масла заполни недостающие поля паспорта и краткое описание.

Масла для обработки (slug → название, текущие данные):
{items}

Заполни для каждого масла:
- botanical_family: ботаническое семейство (например: "Lamiaceae (Яснотковые)")
- origin_countries: страны происхождения (например: "Франция, Болгария")
- extraction_method: метод экстракции (например: "Паровая дистилляция")
- volatility: летучесть — одно из: "Высокая", "Средняя", "Низкая"
- description_short: краткое описание на русском, до 90 символов (если description длинный)

Если поле уже заполнено (не пустое) — верни его значение без изменений.
Если не знаешь точного значения — оставь пустую строку "".

Ответь СТРОГО в формате JSON. Ключ — slug, значение — объект с перечисленными полями.

Пример:
{{
  "lavender": {{
    "botanical_family": "Lamiaceae (Яснотковые)",
    "origin_countries": "Франция, Болгария",
    "extraction_method": "Паровая дистилляция",
    "volatility": "Высокая",
    "description_short": "Успокаивает нервную систему, снимает стресс и улучшает сон"
  }}
}}

Никаких пояснений, только JSON.
"""


def enrich_batch(
    items: list[dict],
    api_key: str,
) -> dict[str, dict]:
    """Send a batch of aroma cards to Claude Haiku. Return {slug: {...}}."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    items_text = "\n".join(
        f"  {item['slug']}: {item['name']}\n"
        f"    botanical_family: {item.get('botanical_family') or '(пусто)'}\n"
        f"    origin_countries: {item.get('origin_countries') or '(пусто)'}\n"
        f"    extraction_method: {item.get('extraction_method') or '(пусто)'}\n"
        f"    volatility: {item.get('volatility') or '(пусто)'}\n"
        f"    description_short: {item.get('description_short') or '(пусто)'}\n"
        f"    description (preview): {str(item.get('description') or '')[:200]}"
        for item in items
    )

    prompt = PROMPT_TEMPLATE.format(items=items_text)

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
        description = str(payload.get("description") or "").strip()

        # Check if any passport field is missing OR description_short is missing/auto-truncated
        missing_passport = any(not payload.get(f) for f in PASSPORT_FIELDS)
        needs_desc_short = (
            len(description) >= 100
            and not str(payload.get("description_short") or "").strip()
        )

        if not force and not missing_passport and not needs_desc_short:
            continue

        work_items.append({
            "slug": m.slug,
            "name": payload.get("name_ru") or payload.get("name") or m.name or m.slug,
            "botanical_family": payload.get("botanical_family") or "",
            "origin_countries": payload.get("origin_countries") or "",
            "extraction_method": payload.get("extraction_method") or "",
            "volatility": payload.get("volatility") or "",
            "description": description,
            "description_short": str(payload.get("description_short") or "").strip(),
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

    all_results: dict[str, dict] = {}
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
            enriched = all_results.get(card_slug)
            if not enriched:
                print(f"  WARNING: no result for {card_slug}")
                continue

            m = model_map.get(card_slug)
            if not m:
                continue

            payload = dict(m.payload or {})
            changed = False
            for field in PASSPORT_FIELDS:
                new_val = str(enriched.get(field) or "").strip()
                if new_val and not payload.get(field):
                    payload[field] = new_val
                    changed = True

            # description_short: only set if not already present
            new_ds = str(enriched.get("description_short") or "").strip()
            if new_ds and not payload.get("description_short"):
                payload["description_short"] = new_ds
                changed = True

            if changed:
                m.payload = payload
                updated += 1
                print(f"  Updated: {card_slug}")

        await session.commit()

    print(f"\nDone. Updated {updated} cards.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich aroma card passport fields via Claude Haiku")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing")
    parser.add_argument("--force", action="store_true", help="Re-enrich cards that already have all fields")
    parser.add_argument("--slug", type=str, default=None, help="Process only a specific card slug")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, force=args.force, slug=args.slug))
