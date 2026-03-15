"""Pre-compute AI summaries for aroma card fields using Claude Haiku.

Generates two types of summaries:
1. `description_short` — comprehensive synthesis of ALL card fields (shown as
   the main description in the card detail view).
2. Per-field summaries (`therapeutic_properties_summary`, `history_summary`,
   `psychological_properties_summary`) — kept for backward compat but no longer
   used in the UI (sections show truncated original text instead).

Usage:
    .venv/bin/python scripts/summarize_aroma_fields.py [--dry-run] [--force]
    .venv/bin/python scripts/summarize_aroma_fields.py --card-summary [--dry-run] [--force]
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

MIN_CHARS = 400  # only summarise fields longer than this
BATCH_SIZE = 10  # items per Claude request (card summaries are larger)

# Per-field summarisation (legacy, kept for backward compat)
PROMPT_TEMPLATE = """\
Ты — редактор-ароматерапевт. Тебе дан список текстовых полей из карточек эфирных масел.
Для каждого поля напиши краткое резюме: 2–3 ёмких предложения, передающих суть.
Не начинай с имени масла. Пиши по-русски. Не используй маркированные списки — только связный текст.

Ответь СТРОГО в формате JSON: объект, где ключ = исходный ID, значение = краткое резюме.
Никаких пояснений, только JSON.

Поля для обработки:
{items}
"""

# Card-level comprehensive synthesis
CARD_SUMMARY_PROMPT = """\
Ты — редактор-ароматерапевт. Тебе даны карточки эфирных масел с разными полями свойств.
Для каждой карточки напиши единое информативное описание: 3–5 предложений, синтезирующих \
ключевую информацию о масле — его характер, психологическое действие, терапевтические свойства, \
основные эффекты и особенности применения.
Не начинай с имени масла. Пиши по-русски. Только связный текст, без маркированных списков.

Ответь СТРОГО в формате JSON: объект, где ключ = slug карточки, значение = описание.
Никаких пояснений, только JSON.

Карточки:
{items}
"""

CARD_SUMMARY_FIELDS = [
    "description",
    "psychological_properties",
    "therapeutic_properties",
    "health_effects",
    "mind_effect",
    "spiritual_emotional",
    "history",
]


def summarise_batch(items: list[dict], api_key: str, prompt_template: str) -> dict[str, str]:
    """Send a batch to Claude Haiku, return {id: summary}."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    items_text = "\n".join(
        f'- ID "{item["id"]}" ({item["field"]}): {item["text"][:1200]}'
        for item in items
    )
    prompt = prompt_template.format(items=items_text)

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


def summarise_card_batch(items: list[dict], api_key: str) -> dict[str, str]:
    """Send a batch of full card data to Claude Haiku for synthesis, return {slug: summary}."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    cards_text = "\n\n".join(
        f'--- Карточка slug="{item["slug"]}" ---\n{item["text"]}'
        for item in items
    )
    prompt = CARD_SUMMARY_PROMPT.format(items=cards_text)

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


async def run_card_summaries(dry_run: bool = False, force: bool = False) -> None:
    """Generate comprehensive description_short for each aroma card."""
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
        models = result.scalars().all()

    print(f"Loaded {len(models)} aroma cards.")

    # Collect cards that need a comprehensive description_short
    work_items: list[dict] = []
    for m in models:
        payload = m.payload or {}
        if not force and payload.get("description_short"):
            continue  # already has a summary

        # Build combined text from all relevant fields
        parts = []
        for field in CARD_SUMMARY_FIELDS:
            val = str(payload.get(field, "") or "").strip()
            if val:
                parts.append(f"{field}: {val[:600]}")

        if not parts:
            continue  # no content to summarise

        work_items.append({
            "slug": m.slug,
            "name": payload.get("name") or m.slug,
            "text": "\n".join(parts),
        })

    print(f"Cards needing description_short: {len(work_items)}")
    if not work_items:
        print("Nothing to do.")
        return

    if dry_run:
        for item in work_items[:10]:
            print(f"  Would summarise card '{item['slug']}' ({len(item['text'])} chars of combined fields)")
        if len(work_items) > 10:
            print(f"  ... and {len(work_items) - 10} more")
        return

    # Process in batches
    all_summaries: dict[str, str] = {}
    for i in range(0, len(work_items), BATCH_SIZE):
        batch = work_items[i : i + BATCH_SIZE]
        print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} cards → Claude Haiku...")
        try:
            result_map = await asyncio.to_thread(summarise_card_batch, batch, api_key)
            all_summaries.update(result_map)
            print(f"    Got {len(result_map)} summaries.")
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
        for slug, summary in all_summaries.items():
            summary = summary.strip()
            if not summary:
                print(f"  WARNING: empty summary for '{slug}'")
                continue
            m = model_map.get(slug)
            if not m:
                continue
            new_payload = dict(m.payload or {})
            new_payload["description_short"] = summary
            m.payload = new_payload
            m.updated_at = datetime.now(timezone.utc)
            updated += 1
        await session.commit()

    print(f"\nDone: {updated} cards updated with description_short.")


async def run(dry_run: bool = False, force: bool = False) -> None:
    """Generate per-field summaries (legacy mode)."""
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
        models = result.scalars().all()

    print(f"Loaded {len(models)} aroma cards.")

    # Collect items that need summarisation
    work_items: list[dict] = []
    for m in models:
        payload = m.payload or {}
        for field, summary_field, min_len in [
            ("therapeutic_properties", "therapeutic_properties_summary", MIN_CHARS),
            ("history", "history_summary", MIN_CHARS),
            ("psychological_properties", "psychological_properties_summary", 200),
        ]:
            text = str(payload.get(field, "") or "").strip()
            if len(text) < min_len:
                continue
            if not force and payload.get(summary_field):
                continue  # already summarised
            work_items.append({
                "id": f"{m.slug}::{field}",
                "slug": m.slug,
                "field": field,
                "summary_field": summary_field,
                "text": text,
            })

    print(f"Fields to summarise: {len(work_items)}")
    if not work_items:
        print("Nothing to do.")
        return

    if dry_run:
        for item in work_items[:10]:
            print(f"  Would summarise {item['id']} ({len(item['text'])} chars)")
        if len(work_items) > 10:
            print(f"  ... and {len(work_items) - 10} more")
        return

    # Process in batches (sync Claude calls via thread executor)
    all_summaries: dict[str, str] = {}
    for i in range(0, len(work_items), 15):
        batch = work_items[i : i + 15]
        print(f"  Batch {i // 15 + 1}: {len(batch)} items → Claude Haiku...")
        try:
            result_map = await asyncio.to_thread(summarise_batch, batch, api_key, PROMPT_TEMPLATE)
            all_summaries.update(result_map)
            print(f"    Got {len(result_map)} summaries.")
        except Exception as e:
            print(f"    ERROR in batch: {e}")

    # Build slug → {summary_field: summary} map
    slug_updates: dict[str, dict] = {}
    for item in work_items:
        summary = all_summaries.get(item["id"], "").strip()
        if not summary:
            print(f"  WARNING: no summary for {item['id']}")
            continue
        slug_updates.setdefault(item["slug"], {})[item["summary_field"]] = summary

    # Write to DB
    updated = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        db_models = result.scalars().all()
        model_map = {m.slug: m for m in db_models}
        for slug, updates in slug_updates.items():
            m = model_map.get(slug)
            if not m:
                continue
            new_payload = dict(m.payload or {})
            new_payload.update(updates)
            m.payload = new_payload
            m.updated_at = datetime.now(timezone.utc)
            updated += 1
        await session.commit()

    print(f"\nDone: {updated} cards updated with per-field summaries.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise aroma card fields via Claude Haiku")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--force", action="store_true", help="Re-summarise even if summary exists")
    parser.add_argument(
        "--card-summary",
        action="store_true",
        help="Generate comprehensive description_short synthesising all card fields (default mode)",
    )
    args = parser.parse_args()

    # Default: generate card-level comprehensive summaries
    if args.card_summary or True:
        asyncio.run(run_card_summaries(dry_run=args.dry_run, force=args.force))
    else:
        asyncio.run(run(dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    main()
