"""Enrich bodywork & sound cards with missing safety data via Claude Haiku.

Fills:
- contraindications: adds critical items if missing (тромбоз, онкология, etc.)
- session_duration: fills from duration_min or generates
- For sound 'voice' cards: fills contraindications and session_duration

Usage:
    .venv/bin/python scripts/enrich_bodywork_safety.py [--dry-run] [--category massage|osteo|biodynamics|sound]
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

BATCH_SIZE = 6
BATCH_DELAY = 1.5

# Critical contraindications by category
CRITICAL_BY_CATEGORY = {
    "massage": ["тромбоз", "онкология", "острое воспаление", "лихорадка"],
    "osteo": ["тромбоз", "онкология", "аневризма", "острый инсульт"],
    "biodynamics": ["онкология", "острый психоз"],
    "sound": ["эпилепсия"],
}

PROMPT_TEMPLATE = """\
Ты — эксперт по {category_ru}. Тебе даны карточки с неполными данными по безопасности.

Для каждой карточки дополни:
1. contraindications — массив строк. Сохрани существующие, добавь недостающие критические.
   Критические для {category_ru}: {critical_items}
2. session_duration — строка, например "30-60 мин". Если есть duration_min, используй его.

Карточки:
{items}

Ответь СТРОГО в формате JSON. Ключ — slug, значение — объект.
Пример:
{{
  "aroma-massage": {{
    "contraindications": ["тромбоз глубоких вен", "онкология", "острое воспаление", "лихорадка", "открытые раны"],
    "session_duration": "45-60 мин"
  }}
}}

Правила:
- Сохрани ВСЕ существующие противопоказания, дополни недостающие
- Противопоказания — конкретные, без общих фраз типа "индивидуальная непереносимость"
- session_duration — реалистичный диапазон для данной техники/практики
- Никаких пояснений, только JSON
"""

CATEGORY_RU = {
    "massage": "массажным техникам",
    "osteo": "остеопатии и остеопрактике",
    "biodynamics": "биодинамике",
    "sound": "звукотерапии и звуковому целительству",
}


def enrich_batch(items: list[dict], category: str) -> dict[str, dict]:
    """Send a batch to Claude via project's call_claude (routes through Replicate)."""
    from bot.services.claude_client import call_claude

    items_text = "\n".join(
        f"  {item['slug']}: {item['name']}\n"
        f"    source_type: {item.get('source_type', '?')}\n"
        f"    existing contraindications: {json.dumps(item.get('contraindications', []), ensure_ascii=False)}\n"
        f"    duration_min: {item.get('duration_min', '(нет)')}\n"
        f"    description (preview): {str(item.get('description', ''))[:200]}"
        for item in items
    )

    prompt = PROMPT_TEMPLATE.format(
        category_ru=CATEGORY_RU.get(category, category),
        critical_items=", ".join(CRITICAL_BY_CATEGORY.get(category, [])),
        items=items_text,
    )

    raw = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        context=f"enrich_bodywork_safety/{category}",
    )

    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
    raw = raw.rstrip("`").strip()
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        raw = json_match.group(0)
    return json.loads(raw)


def _needs_enrichment(payload: dict, category: str) -> list[str]:
    """Return list of reasons this card needs enrichment."""
    reasons = []
    contra = payload.get("contraindications") or []
    if isinstance(contra, str):
        contra = [contra]

    # Check missing critical contraindications
    contra_text = " ".join(contra).lower()
    critical = CRITICAL_BY_CATEGORY.get(category, [])
    missing = [c for c in critical if c not in contra_text]
    if missing:
        reasons.append(f"missing critical contraindications: {', '.join(missing)}")

    if not contra:
        reasons.append("no contraindications at all")

    # Check session_duration
    has_duration = payload.get("session_duration") or payload.get("duration_min")
    if not has_duration:
        reasons.append("no session_duration")

    return reasons


async def run(dry_run: bool = False, category: str | None = None) -> None:
    from config import settings
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    if not settings.replicate_api_key and not settings.anthropic_api_key:
        raise RuntimeError("Neither REPLICATE_API_KEY nor ANTHROPIC_API_KEY is set")

    categories = [category] if category else ["massage", "osteo", "biodynamics", "sound"]

    for cat in categories:
        print(f"\n{'='*60}")
        print(f"Category: {cat}")
        print(f"{'='*60}")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.category == cat)
            )
            all_models = result.scalars().all()

        print(f"Total cards: {len(all_models)}")

        work_items: list[dict] = []
        for m in all_models:
            payload = m.payload or {}
            reasons = _needs_enrichment(payload, cat)
            if not reasons:
                continue

            work_items.append({
                "slug": m.slug,
                "name": payload.get("name_ru") or payload.get("name") or m.name or m.slug,
                "source_type": m.source_type or payload.get("source_type", ""),
                "contraindications": payload.get("contraindications") or [],
                "duration_min": payload.get("duration_min"),
                "description": str(payload.get("description") or "")[:300],
                "reasons": reasons,
            })

        print(f"Cards needing enrichment: {len(work_items)}")
        if not work_items:
            print("Nothing to do.")
            continue

        if dry_run:
            for item in work_items:
                print(f"  {item['slug']} ({item['name']}): {', '.join(item['reasons'])}")
            continue

        all_results: dict[str, dict] = {}
        for i in range(0, len(work_items), BATCH_SIZE):
            batch = work_items[i: i + BATCH_SIZE]
            print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} cards -> Claude Haiku...")
            try:
                batch_result = await asyncio.to_thread(enrich_batch, batch, cat)
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
                select(AromaCardModel).where(AromaCardModel.category == cat)
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

                # Update contraindications
                new_contra = enriched.get("contraindications")
                if new_contra and isinstance(new_contra, list):
                    old_contra = payload.get("contraindications") or []
                    if isinstance(old_contra, str):
                        old_contra = [old_contra]
                    # Merge: keep existing, add new
                    existing_lower = {c.lower() for c in old_contra}
                    merged = list(old_contra)
                    for c in new_contra:
                        if c.lower() not in existing_lower:
                            merged.append(c)
                            existing_lower.add(c.lower())
                    if len(merged) > len(old_contra):
                        payload["contraindications"] = merged
                        changed = True

                # Update session_duration
                new_dur = enriched.get("session_duration")
                if new_dur and not payload.get("session_duration"):
                    payload["session_duration"] = new_dur
                    changed = True

                if changed:
                    m.payload = payload
                    updated += 1
                    print(f"  Updated: {card_slug}")

            await session.commit()

        print(f"Updated {updated} cards in {cat}.")

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich bodywork & sound cards with safety data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    parser.add_argument("--category", type=str, default=None, help="Process only specific category")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, category=args.category))
