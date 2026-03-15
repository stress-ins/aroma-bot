"""Fix KB data quality issues in aroma.db:
1. description_short — comprehensive AI synthesis for cards missing it
2. name_ru — fill for blends that have none
3. broken cross-refs — null-out ingredient_slugs/symptom refs pointing to non-existent cards

Usage:
    .venv/bin/python scripts/fix_data_quality.py [--dry-run] [--force]
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

SUMMARY_FIELDS = [
    "description", "psychological_properties", "therapeutic_properties",
    "health_effects", "mind_effect", "spiritual_emotional", "history",
]

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

BLEND_NAME_RU_MAP = {
    "blend-aroma-life":    "Арома Лайф",
    "blend-awaken":        "Пробуждение",
    "blend-cool-azul":     "Кул Азул",
    "blend-lady-sclareol": "Леди Скларэол",
    "blend-thieves":       "Тиевс",
}

BATCH_SIZE = 10


def _call_claude(items: list[dict], api_key: str) -> dict[str, str]:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    cards_text = "\n\n".join(
        f'--- slug="{it["slug"]}" ---\n{it["text"]}'
        for it in items
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": CARD_SUMMARY_PROMPT.format(items=cards_text)}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
    raw = raw.rstrip("`").strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    return json.loads(raw)


async def run(dry_run: bool = False, force: bool = False) -> None:
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

    all_slugs = {m.slug for m in all_models}
    updates: dict[str, dict] = {}

    # 1. Broken cross-refs
    fixed_refs = 0
    for m in all_models:
        p = dict(m.payload or {})
        changed = False
        if m.category == "blend":
            ingr = p.get("ingredient_slugs") or []
            new_ingr = [s if (not s or s in all_slugs) else None for s in ingr]
            if new_ingr != ingr:
                p["ingredient_slugs"] = new_ingr
                changed = True
        if m.category == "symptom":
            for field in ("recommended_oil_slugs", "recommended_blend_slugs"):
                old = p.get(field) or []
                new = [s for s in old if not s or s in all_slugs]
                if new != old:
                    p[field] = new
                    changed = True
        if changed:
            updates.setdefault(m.slug, {}).update(p)
            fixed_refs += 1
    print(f"[cross-refs] {fixed_refs} cards with broken refs")

    # 2. Blend name_ru
    fixed_name_ru = 0
    for m in all_models:
        if m.category != "blend":
            continue
        p = dict(m.payload or {})
        if (p.get("name_ru") or "").strip():
            continue
        name_ru = BLEND_NAME_RU_MAP.get(m.slug) or m.slug.replace("-", " ").capitalize()
        p["name_ru"] = name_ru
        if not (p.get("name") or "").strip():
            p["name"] = name_ru
        updates.setdefault(m.slug, {}).update(p)
        fixed_name_ru += 1
        print(f"  name_ru: {m.slug} → {name_ru!r}")
    print(f"[name_ru] {fixed_name_ru} blends")

    # 3. description_short
    work = []
    for m in all_models:
        if m.category != "aroma":
            continue
        p = dict(m.payload or {})
        if not force and len((p.get("description_short") or "").strip()) >= 10:
            continue
        parts = [f"{f}: {str(p.get(f) or '')[:600]}" for f in SUMMARY_FIELDS if str(p.get(f) or "").strip()]
        if parts:
            work.append({"slug": m.slug, "payload": p, "text": "\n".join(parts)})
    print(f"[description_short] {len(work)} aroma cards")

    if dry_run:
        print("Dry run — no changes written.")
        return

    all_summaries: dict[str, str] = {}
    for i in range(0, len(work), BATCH_SIZE):
        batch = work[i:i + BATCH_SIZE]
        print(f"  batch {i // BATCH_SIZE + 1}: {len(batch)} cards → Claude Haiku...")
        try:
            result_map = await asyncio.to_thread(_call_claude, batch, api_key)
            all_summaries.update(result_map)
            print(f"    got {len(result_map)} summaries")
        except Exception as e:
            print(f"    ERROR: {e}")

    for item in work:
        summary = all_summaries.get(item["slug"], "").strip()
        if summary:
            item["payload"]["description_short"] = summary
            updates.setdefault(item["slug"], {}).update(item["payload"])

    written = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AromaCardModel))
        db_models = result.scalars().all()
        db_map = {m.slug: m for m in db_models}
        for slug, patch in updates.items():
            m = db_map.get(slug)
            if not m:
                continue
            new_payload = dict(m.payload or {})
            new_payload.update(patch)
            m.payload = new_payload
            m.updated_at = datetime.now(timezone.utc)
            written += 1
        await session.commit()

    print(f"\nDone: {written} cards updated.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    main()
