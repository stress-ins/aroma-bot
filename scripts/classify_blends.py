"""Classify blend cards into functional categories using Claude Haiku.

Reads all blend card names from DB, sends a single Claude Haiku request to
classify each into a functional category, then writes blend_category back
to all matching blend cards.

Usage:
    .venv/bin/python scripts/classify_blends.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


CATEGORIES = [
    "ЭМОЦИИ И НАСТРОЕНИЕ",
    "ЭНЕРГИЯ И МОТИВАЦИЯ",
    "РАССЛАБЛЕНИЕ И СОН",
    "ЗДОРОВЬЕ И ИММУНИТЕТ",
    "БОЛЬ И ВОССТАНОВЛЕНИЕ",
    "ДЫХАНИЕ И ГОЛОВА",
    "ЖЕНСКОЕ ЗДОРОВЬЕ",
    "МУЖСКОЕ ЗДОРОВЬЕ",
    "ДЕТСКАЯ КОЛЛЕКЦИЯ",
    "ДУХОВНОСТЬ",
    "КРАСОТА И УХОД",
]

VALID_CATEGORIES = set(CATEGORIES)

PROMPT = """\
Ты — классификатор эфирных масел Young Living. Тебе дан список смесей (blends) Young Living.
Твоя задача — отнести каждую смесь к одной из функциональных категорий.

Используй ТОЛЬКО следующие категории:
- ЭМОЦИИ И НАСТРОЕНИЕ — смеси для работы с чувствами: радость, прощение, принятие, гармония
- ЭНЕРГИЯ И МОТИВАЦИЯ — мотивация, вдохновение, уверенность, цели, будущее
- РАССЛАБЛЕНИЕ И СОН — расслабление, стресс, тревога, сон, покой, заземление
- ЗДОРОВЬЕ И ИММУНИТЕТ — иммунитет, детокс, антибактериальный, очищение, долголетие
- БОЛЬ И ВОССТАНОВЛЕНИЕ — боль в мышцах, суставах, головная боль, травмы
- ДЫХАНИЕ И ГОЛОВА — дыхание, лёгкие, синусы, ментальная ясность, фокус
- ЖЕНСКОЕ ЗДОРОВЬЕ — гормоны, женский цикл, репродуктивное здоровье
- ДЕТСКАЯ КОЛЛЕКЦИЯ — смеси специально для детей (KidScents, Seedlings, Gentle Baby)
- ДУХОВНОСТЬ — медитация, духовные практики, чакры, высшая цель
- МУЖСКОЕ ЗДОРОВЬЕ — мужское здоровье, тестостерон, мужские смеси
- КРАСОТА И УХОД — кожа, красота, тело

Правила:
- Каждой смеси присвой ровно одну категорию из списка выше.
- Если смесь не подходит ни под одну — используй "ЭМОЦИИ И НАСТРОЕНИЕ".
- Ответь СТРОГО в формате JSON: объект где ключ = исходное название смеси, значение = категория.
- Никаких пояснений, только JSON.

Смеси для классификации:
{blends}
"""


async def classify_with_claude(blend_names: list[str]) -> dict[str, str]:
    import anthropic
    from config import settings

    api_key = settings.anthropic_api_key
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    blends_text = "\n".join(f"- {n}" for n in blend_names)

    print(f"Sending {len(blend_names)} blends to Claude Haiku...")
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": PROMPT.format(blends=blends_text)}],
    )

    import re
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
    raw = raw.rstrip("`").strip()
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        raw = json_match.group(0)

    return json.loads(raw)


async def run(dry_run: bool = False) -> None:
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select
    from datetime import datetime, timezone

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "blend")
        )
        blend_models = result.scalars().all()

    if not blend_models:
        print("No blend cards in DB.")
        return

    blend_names = [m.name for m in blend_models]
    print(f"Found {len(blend_names)} blend cards.")

    mapping = await classify_with_claude(blend_names)

    # Normalize unknown categories to closest valid one
    for name, cat in list(mapping.items()):
        if cat not in VALID_CATEGORIES:
            print(f"  Normalizing unknown category '{cat}' for '{name}' → ЭМОЦИИ И НАСТРОЕНИЕ")
            mapping[name] = "ЭМОЦИИ И НАСТРОЕНИЕ"

    missing = [n for n in blend_names if n not in mapping]
    if missing:
        print(f"WARNING: Claude did not classify {len(missing)} blends: {missing[:5]}")
        for n in missing:
            mapping[n] = "ЭМОЦИИ И НАСТРОЕНИЕ"

    from collections import Counter
    cat_counts = Counter(mapping.values())
    print("\nClassification summary:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count} blends")

    if dry_run:
        print("\n--- DRY RUN — no DB writes ---")
        for m in blend_models:
            print(f"  {m.name} → {mapping.get(m.name, '?')}")
        return

    updated = 0
    skipped = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "blend")
        )
        models = result.scalars().all()
        for m in models:
            cat = mapping.get(m.name, "ЭМОЦИИ И НАСТРОЕНИЕ")
            new_payload = dict(m.payload or {})
            if new_payload.get("blend_category") == cat:
                skipped += 1
                continue
            new_payload["blend_category"] = cat
            m.payload = new_payload
            m.updated_at = datetime.now(timezone.utc)
            updated += 1
        await session.commit()

    print(f"\nDone: {updated} blends updated, {skipped} skipped (already set).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify blend categories via Claude Haiku")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
