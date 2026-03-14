#!/usr/bin/env python3
"""Seed the 'Смесь от морщин' blend and update the морщины symptom cross-reference.

Usage:
    .venv/bin/python scripts/seed_wrinkles_blend.py [--dry-run]

This script:
1. Upserts the blend card smesh-ot-morshchin into the DB
2. Ensures symptom-морщины has recommended_blend_slugs = ["smesh-ot-morshchin"]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BLEND_SLUG = "smesh-ot-morshchin"
SYMPTOM_SLUG = "symptom-морщины"


async def run(dry_run: bool = False) -> None:
    from sqlalchemy import select
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel

    blend_payload = {
        "name_ru": "Смесь от морщин",
        "name_en": "Anti-Wrinkle Blend",
        "key": "Смесь от морщин",
        "description": (
            "Антивозрастная смесь эфирных масел для борьбы с морщинами. "
            "Сочетает Sacred Frankincense, Sandalwood, Geranium и Lavender — "
            "масла, известные своими регенерирующими и омолаживающими свойствами для кожи."
        ),
        "therapeutic_properties": "регенерация кожи, антивозрастное, увлажняющее, противовоспалительное, тонизирующее",
        "conditions_for_use": "Морщины, дряблость кожи, пигментные пятна, сухость кожи",
        "applications": (
            "• Нанести 2–3 капли на проблемные зоны лица, разбавив с базовым маслом 1:4\n"
            "• Добавить в ночной крем 1–2 капли\n"
            "• Массаж лица с базовым маслом"
        ),
        "ingredient_names": ["Sacred Frankincense", "Sandalwood", "Geranium", "Lavender"],
        "ingredient_drops": [6, 5, 4, 3],
        "ingredient_slugs": ["sacred-frankincense", "sandalwood", "geranium", "lavender"],
        "complementary_oil_names": [],
        "complementary_oil_slugs": [],
        "precautions": "Разбавлять базовым маслом перед нанесением на кожу. Избегать зоны глаз.",
        "blend_category": "Красота и уход за кожей",
        "category_group": "beauty",
        "source_pdf": "handbook",
    }

    async with AsyncSessionLocal() as session:
        # 1. Upsert blend card
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == BLEND_SLUG)
        )
        blend = result.scalar_one_or_none()
        if blend:
            print(f"Blend {BLEND_SLUG} already exists — updating payload.")
            if not dry_run:
                blend.payload = blend_payload
                blend.updated_at = datetime.now(timezone.utc)
        else:
            print(f"Creating blend {BLEND_SLUG}.")
            if not dry_run:
                session.add(AromaCardModel(
                    slug=BLEND_SLUG,
                    name="Смесь от морщин",
                    category="blend",
                    source_type="blend",
                    aliases=[],
                    payload=blend_payload,
                ))

        # 2. Update symptom cross-reference
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == SYMPTOM_SLUG)
        )
        symptom = result.scalar_one_or_none()
        if symptom:
            new_payload = dict(symptom.payload or {})
            blend_slugs = list(new_payload.get("recommended_blend_slugs") or [])
            if BLEND_SLUG not in blend_slugs:
                blend_slugs.append(BLEND_SLUG)
                print(f"Adding {BLEND_SLUG} to {SYMPTOM_SLUG}.recommended_blend_slugs.")
                if not dry_run:
                    new_payload["recommended_blend_slugs"] = blend_slugs
                    blend_names = list(new_payload.get("recommended_blend_names") or [])
                    if "Смесь от морщин" not in blend_names:
                        blend_names.append("Смесь от морщин")
                    new_payload["recommended_blend_names"] = blend_names
                    symptom.payload = new_payload
                    symptom.updated_at = datetime.now(timezone.utc)
            else:
                print(f"{SYMPTOM_SLUG} already references {BLEND_SLUG}.")
        else:
            print(f"WARNING: symptom {SYMPTOM_SLUG} not found in DB — run import_handbook_data.py first.")

        if not dry_run:
            await session.commit()
            print("Done.")
        else:
            print("Dry run — no changes written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed wrinkles blend card")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
