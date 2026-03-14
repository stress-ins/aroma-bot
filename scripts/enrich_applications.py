"""Enrich card applications (and description for symptoms) via Claude Haiku.

Fills empty `applications` field for symptom/aroma/blend cards.
For symptoms also fills `description` when missing.

Usage:
    .venv/bin/python scripts/enrich_applications.py [--dry-run] [--category symptom|aroma|blend] [--slug SLUG]
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
BATCH_DELAY = 2.0

SYMPTOM_PROMPT_TEMPLATE = """\
Ты — эксперт-ароматерапевт. Тебе дан список симптомов/состояний.
Для каждого симптома напиши на РУССКОМ ЯЗЫКЕ:
1. description: 2-3 предложения — что это за состояние, как проявляется
2. applications: 3-4 способа применения эфирных масел (ингаляция, топикально, диффузор, ванна и т.д.)

Симптомы для обработки (slug → название, группа, рекомендуемые масла):
{items}

Если поле уже заполнено (не пустое) — верни его значение без изменений.
Описание (description) пиши в Title Case для имён, начало каждого предложения с заглавной буквы.
Применение (applications) — список через "• ", каждый пункт на новой строке.

Ответь СТРОГО в формате JSON. Ключ — slug, значение — объект с полями description и applications.

Пример:
{{
  "headache": {{
    "description": "Головная боль — неприятное болезненное ощущение в области головы. Может быть вызвана стрессом, напряжением мышц или нарушением кровообращения.",
    "applications": "• Ингаляция: 2-3 капли лаванды на ткань, вдыхать 5-10 минут\\n• Топикально: смесь с базовым маслом нанести на виски и затылок\\n• Диффузор: перечная мята + лаванда, 30 минут\\n• Холодный компресс: 2 капли масла перечной мяты на влажную ткань"
  }}
}}

Никаких пояснений, только JSON.
"""

AROMA_BLEND_PROMPT_TEMPLATE = """\
Ты — эксперт-ароматерапевт. Тебе дан список эфирных масел / смесей.
Для каждого напиши на РУССКОМ ЯЗЫКЕ способы применения (applications):
3-4 пункта (ингаляция, топикально, диффузор, ванна и т.д.) с дозировками если известно.

Карточки для обработки (slug → название):
{items}

Применение (applications) — список через "• ", каждый пункт на новой строке.

Ответь СТРОГО в формате JSON. Ключ — slug, значение — объект с полем applications.

Пример:
{{
  "lavender": {{
    "applications": "• Диффузор: 3-5 капель, 30-60 минут\\n• Топикально: 2-3 капли в 10 мл базового масла, массаж\\n• Ванна: 5-7 капель в соль для ванны\\n• Ингаляция: 1-2 капли на ткань или в аромамедальон"
  }}
}}

Никаких пояснений, только JSON.
"""


def _parse_json_response(raw: str) -> dict:
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
    raw = raw.rstrip("`").strip()
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        raw = json_match.group(0)
    return json.loads(raw)


def enrich_batch(items: list[dict], category: str, api_key: str) -> dict[str, dict]:
    """Send a batch of cards to Claude Haiku. Return {slug: {...}}."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    if category == "symptom":
        items_text = "\n".join(
            f"  {item['slug']}: {item['name']}\n"
            f"    group: {item.get('category_group') or '(нет)'}\n"
            f"    oils: {', '.join(item.get('recommended_oils', [])[:5]) or '(нет)'}\n"
            f"    description: {item.get('description') or '(пусто)'}"
            for item in items
        )
        prompt = SYMPTOM_PROMPT_TEMPLATE.format(items=items_text)
    else:
        items_text = "\n".join(
            f"  {item['slug']}: {item['name']}"
            for item in items
        )
        prompt = AROMA_BLEND_PROMPT_TEMPLATE.format(items=items_text)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    return _parse_json_response(raw)


async def run(
    dry_run: bool = False,
    category: str = "symptom",
    slug: str | None = None,
) -> None:
    from config import settings
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    api_key = settings.anthropic_api_key
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == category)
        )
        all_models = result.scalars().all()

    print(f"Loaded {len(all_models)} {category} cards.")

    if slug:
        candidates = [m for m in all_models if m.slug == slug]
        if not candidates:
            print(f"ERROR: no {category} card found with slug={slug!r}")
            return
    else:
        candidates = all_models

    work_items: list[dict] = []
    for m in candidates:
        payload = m.payload or {}
        applications = str(payload.get("applications") or "").strip()
        description = str(payload.get("description") or "").strip()

        needs_applications = not applications
        needs_description = (category == "symptom") and not description

        if not needs_applications and not needs_description:
            continue

        item: dict = {
            "slug": m.slug,
            "name": payload.get("name_ru") or payload.get("name") or m.name or m.slug,
            "applications": applications,
        }
        if category == "symptom":
            item["description"] = description
            item["category_group"] = payload.get("category_group") or ""
            # Gather recommended oil names from linked oils
            oil_names = []
            for oil in (payload.get("oils") or []):
                n = oil.get("name_ru") or oil.get("name") or ""
                if n:
                    oil_names.append(n)
            item["recommended_oils"] = oil_names

        work_items.append(item)

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
            batch_result = await asyncio.to_thread(enrich_batch, batch, category, api_key)
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
            select(AromaCardModel).where(AromaCardModel.category == category)
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

            new_apps = str(enriched.get("applications") or "").strip()
            if new_apps and not str(payload.get("applications") or "").strip():
                payload["applications"] = new_apps
                changed = True

            if category == "symptom":
                new_desc = str(enriched.get("description") or "").strip()
                if new_desc and not str(payload.get("description") or "").strip():
                    # KB-002: normalize — capitalize first letter of description
                    payload["description"] = new_desc[:1].upper() + new_desc[1:]
                    changed = True

            if changed:
                m.payload = payload
                updated += 1
                print(f"  Updated: {card_slug}")

        await session.commit()

    print(f"\nDone. Updated {updated} cards.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich card applications via Claude Haiku")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing")
    parser.add_argument("--category", type=str, default="symptom", choices=["symptom", "aroma", "blend"],
                        help="Card category to process")
    parser.add_argument("--slug", type=str, default=None, help="Process only a specific card slug")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, category=args.category, slug=args.slug))
