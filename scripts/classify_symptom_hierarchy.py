"""Classify symptom category_groups into anatomical parent_groups using Claude Haiku.

Reads all unique category_group values from symptom cards in DB, sends a single
Claude Haiku request to classify each into an anatomical body system (parent_group),
then writes parent_group back to all matching symptom cards.

Usage:
    .venv/bin/python scripts/classify_symptom_hierarchy.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


PROMPT = """\
Ты — медицинский классификатор. Тебе дан список медицинских категорий болезней и симптомов на русском языке.
Твоя задача — отнести каждую категорию к одной из анатомических систем организма.

Используй ТОЛЬКО следующие анатомические системы в качестве parent_group:
- НЕРВНАЯ СИСТЕМА
- КРОВЕНОСНАЯ И СЕРДЕЧНО-СОСУДИСТАЯ СИСТЕМА
- ДЫХАТЕЛЬНАЯ СИСТЕМА
- ПИЩЕВАРИТЕЛЬНАЯ СИСТЕМА
- ОПОРНО-ДВИГАТЕЛЬНАЯ СИСТЕМА
- ЭНДОКРИННАЯ СИСТЕМА
- ИММУННАЯ СИСТЕМА
- РЕПРОДУКТИВНАЯ СИСТЕМА
- МОЧЕВЫДЕЛИТЕЛЬНАЯ СИСТЕМА
- КОЖА И ПОКРОВЫ
- ОРГАНЫ ЗРЕНИЯ И СЛУХА
- ПСИХИКА И ЭМОЦИИ
- ОБЩЕЕ И РАЗНОЕ

Правила:
- Каждой категории присвой ровно один parent_group из списка выше.
- Если категория не подходит ни под одну систему — используй "ОБЩЕЕ И РАЗНОЕ".
- Ответь СТРОГО в формате JSON: объект где ключ = исходная категория, значение = parent_group.
- Никаких пояснений, только JSON.

Категории для классификации:
{categories}
"""


async def classify_with_claude(categories: list[str]) -> dict[str, str]:
    """Send all categories to Claude Haiku in one request, get category→parent_group mapping."""
    import anthropic
    from config import settings

    api_key = settings.anthropic_api_key
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env or environment")

    client = anthropic.Anthropic(api_key=api_key)
    categories_text = "\n".join(f"- {c}" for c in categories)

    print(f"Sending {len(categories)} categories to Claude Haiku...")
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": PROMPT.format(categories=categories_text),
        }],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
    raw = raw.rstrip("`").strip()

    # Extract JSON object even if there's surrounding text
    import re
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        raw = json_match.group(0)

    mapping: dict[str, str] = json.loads(raw)
    return mapping


async def run(dry_run: bool = False) -> None:
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select
    from datetime import datetime, timezone

    # 1. Load all symptom cards from DB
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "symptom")
        )
        symptom_models = result.scalars().all()

    if not symptom_models:
        print("No symptom cards in DB.")
        return

    # 2. Collect unique non-empty category_groups
    category_groups: set[str] = set()
    for m in symptom_models:
        cg = str((m.payload or {}).get("category_group", "")).strip()
        if cg:
            category_groups.add(cg)

    if not category_groups:
        print("No category_groups found in symptom cards.")
        return

    sorted_groups = sorted(category_groups)
    print(f"Found {len(sorted_groups)} unique category_groups, {len(symptom_models)} total symptom cards.")

    # 3. Classify via Claude Haiku
    mapping = await classify_with_claude(sorted_groups)

    # Validate: every key in sorted_groups should be in mapping
    missing = [g for g in sorted_groups if g not in mapping]
    if missing:
        print(f"WARNING: Claude did not classify {len(missing)} groups: {missing[:5]}")
        # Fall back to ОБЩЕЕ И РАЗНОЕ for missing ones
        for g in missing:
            mapping[g] = "ОБЩЕЕ И РАЗНОЕ"

    # Print mapping summary
    from collections import Counter
    system_counts = Counter(mapping.values())
    print("\nClassification summary:")
    for system, count in sorted(system_counts.items(), key=lambda x: -x[1]):
        print(f"  {system}: {count} category_groups")

    if dry_run:
        print("\n--- DRY RUN — no DB writes ---")
        for m in symptom_models:
            cg = str((m.payload or {}).get("category_group", "")).strip()
            pg = mapping.get(cg, "ОБЩЕЕ И РАЗНОЕ") if cg else ""
            if pg:
                print(f"  {m.slug}: category_group={cg!r} → parent_group={pg!r}")
        return

    # 4. Write parent_group to DB
    updated = 0
    skipped = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "symptom")
        )
        models = result.scalars().all()
        for m in models:
            cg = str((m.payload or {}).get("category_group", "")).strip()
            if not cg:
                skipped += 1
                continue
            pg = mapping.get(cg, "ОБЩЕЕ И РАЗНОЕ")
            new_payload = dict(m.payload or {})
            if new_payload.get("parent_group") == pg:
                skipped += 1
                continue
            new_payload["parent_group"] = pg
            m.payload = new_payload
            m.updated_at = datetime.now(timezone.utc)
            updated += 1
        await session.commit()

    print(f"\nDone: {updated} cards updated, {skipped} skipped (no category_group or already set).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify symptom parent_group hierarchy via Claude Haiku")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
