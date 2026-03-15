"""Extract symptom conditions from aroma card descriptions and link to symptom cards.

For each aroma card with health-related content, uses Claude Haiku to extract
condition/symptom names and matches them to existing symptom cards.
Adds the oil slug to `recommended_oil_slugs` on matched symptom cards.

Usage:
    .venv/bin/python scripts/enrich_symptom_oil_links.py [--dry-run] [--slug SLUG]
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

SOURCE_FIELDS = [
    "therapeutic_properties",
    "health_effects",
    "conditions_for_use",
    "psychological_properties",
]

EXTRACT_PROMPT = """\
Ты — помощник ароматерапевта. Тебе дана карточка эфирного масла с текстом свойств.

Твоя задача — найти все состояния/симптомы/заболевания, при которых это масло применяется,
и сопоставить их с карточками симптомов из базы.

ТЕКСТ МАСЛА ({oil_name}):
{oil_text}

СПИСОК КАРТОЧЕК СИМПТОМОВ (slug: название):
{symptom_list}

Верни СТРОГО JSON: список slug'ов карточек симптомов, которые соответствуют состояниям,
упомянутым в тексте масла. Включай только явные соответствия.
Формат: {{"matched_slugs": ["slug1", "slug2", ...]}}
Никаких пояснений, только JSON.
"""


def call_claude(oil_name: str, oil_text: str, symptom_list: str, api_key: str) -> list[str]:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    prompt = EXTRACT_PROMPT.format(
        oil_name=oil_name,
        oil_text=oil_text[:3000],
        symptom_list=symptom_list,
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
    raw = raw.rstrip("`").strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    data = json.loads(raw)
    return data.get("matched_slugs", [])


async def run(dry_run: bool = False, slug_filter: str | None = None) -> None:
    from config import settings
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select
    from datetime import datetime, timezone

    api_key = settings.anthropic_api_key
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel))
        all_models = result.scalars().all()

    # Build symptom lookup: slug → {name, payload}
    symptom_cards = {m.slug: m for m in all_models if m.category == "symptom"}
    # Symptom list string for prompt (slug: name)
    symptom_list_str = "\n".join(
        f"{slug}: {m.name}"
        for slug, m in sorted(symptom_cards.items(), key=lambda x: x[1].name or "")
    )

    # Build current oil→symptoms reverse map
    oil_to_symptom_slugs: dict[str, set[str]] = {}
    for slug, m in symptom_cards.items():
        p = m.payload or {}
        for oil_slug in (p.get("recommended_oil_slugs") or []):
            if oil_slug:
                oil_to_symptom_slugs.setdefault(oil_slug, set()).add(slug)

    # Aroma cards to process
    aroma_cards = [m for m in all_models if m.category == "aroma"]
    if slug_filter:
        aroma_cards = [m for m in aroma_cards if m.slug == slug_filter]

    # Filter to cards with health-related content
    to_process = []
    for m in aroma_cards:
        p = m.payload or {}
        text = " ".join(str(p.get(f) or "") for f in SOURCE_FIELDS).strip()
        if len(text) > 50:
            to_process.append((m, text))

    print(f"Aroma cards with health content: {len(to_process)}")

    updates: dict[str, dict] = {}  # symptom_slug → payload updates

    for i, (aroma_m, oil_text) in enumerate(to_process):
        oil_name = (aroma_m.payload or {}).get("name") or aroma_m.name or aroma_m.slug
        print(f"[{i+1}/{len(to_process)}] {aroma_m.slug} ({oil_name}) — {len(oil_text)} chars")
        try:
            matched = await asyncio.to_thread(
                call_claude, oil_name, oil_text, symptom_list_str, api_key
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        # Validate matched slugs exist
        valid = [s for s in matched if s in symptom_cards]
        new_links = [s for s in valid if aroma_m.slug not in oil_to_symptom_slugs.get(s, set())]

        print(f"  matched {len(valid)} symptoms, {len(new_links)} new links")
        if new_links:
            print(f"  → {new_links}")

        if not dry_run:
            for sym_slug in new_links:
                sym_m = symptom_cards[sym_slug]
                p = dict(sym_m.payload or {})
                names = list(p.get("recommended_oil_names") or [])
                slugs = list(p.get("recommended_oil_slugs") or [])
                # Avoid duplicates
                if aroma_m.slug not in slugs:
                    oil_ru_name = (aroma_m.payload or {}).get("name_ru") or (aroma_m.payload or {}).get("name") or aroma_m.name or aroma_m.slug
                    names.append(oil_ru_name)
                    slugs.append(aroma_m.slug)
                    p["recommended_oil_names"] = names
                    p["recommended_oil_slugs"] = slugs
                    updates[sym_slug] = p
                    # Update local reverse map
                    oil_to_symptom_slugs.setdefault(aroma_m.slug, set()).add(sym_slug)

    if dry_run:
        print(f"\nDry run — no changes written. Would update {sum(1 for _ in updates)} symptom cards.")
        return

    # Write to DB
    written = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel))
        db_models = result.scalars().all()
        db_map = {m.slug: m for m in db_models}
        for sym_slug, new_payload in updates.items():
            m = db_map.get(sym_slug)
            if not m:
                continue
            m.payload = new_payload
            m.updated_at = datetime.now(timezone.utc)
            written += 1
        await session.commit()

    print(f"\nDone: {written} symptom cards updated with new oil links.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--slug", help="Process only this aroma slug")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, slug_filter=args.slug))


if __name__ == "__main__":
    main()
