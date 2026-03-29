"""One-time script: fill missing psychological_properties, resource_values, history
for PDF-import aroma cards via Claude API.

Idempotent: skips cards where all three fields are already populated.
Run: .venv/bin/python scripts/enrich_psychological_data.py [--force] [--slug=blue-tansy]
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from db.models import AromaCardModel
from db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# 24 PDF-import slugs that are missing psychological data
PDF_IMPORT_SLUGS = [
    "angelica", "blue-tansy", "caraway", "carrot-seed", "cistus", "davana",
    "dill", "elemi", "eucaliptus-blue", "hong-kuai", "laurus", "ledum",
    "manuka", "melissa", "myrtle", "palmarosa", "palo-santo", "petitgrain",
    "ravintsara", "roman-chamomile", "sacred-frankincense", "spearmint",
    "valerian", "wintergreen",
]

SYSTEM_PROMPT = """\
Ты -- опытный аромадиагност и врач-натуропат с 20-летним стажем. \
Ты пишешь профессиональные описания эфирных масел для справочника ароматерапевта.

Стиль:
- Пиши на русском языке
- Используй профессиональный, но доступный язык
- Упоминай чакры, энергетические свойства, психоэмоциональное воздействие
- НЕ используй медицинские утверждения без оговорок ("может помочь", "традиционно применяется")
- Тон -- как у опытного наставника, который делится знаниями с коллегами

Формат ответа -- строго JSON (без markdown, без ```json```):
{
  "psychological_properties": "...",
  "resource_values": {
    "plus": "...",
    "minus": "..."
  },
  "history": "..."
}
"""

USER_PROMPT_TEMPLATE = """\
Напиши три блока для эфирного масла {name_ru} ({name_en}):

1. **psychological_properties** (100-300 слов): Психологические и энергетические свойства масла. \
Какие эмоциональные состояния оно корректирует, какие чакры активирует, \
как влияет на внутреннее состояние человека. Стиль -- как в справочнике аромадиагноста.

2. **resource_values** -- словарь с двумя ключами:
   - **plus** (50-150 слов): Ресурсное состояние -- что означает, когда человек выбирает это масло \
в ресурсном, наполненном состоянии. "Мы полны..." / "Человек ощущает..."
   - **minus** (50-150 слов): Дефицитное состояние -- что означает, когда масло выходит в минус, \
какие проблемы и нехватки оно компенсирует. "Признаки..." / "В этом состоянии..."

3. **history** (100-200 слов): История использования масла -- от древних времён до наших дней. \
Этимология названия, традиционное применение, интересные факты.

Контекст масла:
- Ботаническое семейство: {botanical_family}
- Метод получения: {extraction_method}
- Ключевая тема: {key}
- Терапевтические свойства: {therapeutic_properties}

Верни строго JSON без обёрток.
"""


def _build_prompt(card: AromaCardModel) -> str:
    """Build user prompt from card data."""
    payload = card.payload or {}
    return USER_PROMPT_TEMPLATE.format(
        name_ru=payload.get("name_ru", card.name),
        name_en=payload.get("name_en", card.slug.replace("-", " ").title()),
        botanical_family=payload.get("botanical_family", "не указано"),
        extraction_method=payload.get("extraction_method", "не указано"),
        key=payload.get("key", card.name),
        therapeutic_properties=(payload.get("therapeutic_properties", "")[:500] or "не указано"),
    )


def _is_populated(card: AromaCardModel) -> bool:
    """Check if card already has all three fields filled."""
    payload = card.payload or {}
    psych = (payload.get("psychological_properties") or "").strip()
    rv = payload.get("resource_values") or {}
    plus_val = (rv.get("plus") or "").strip()
    minus_val = (rv.get("minus") or "").strip()
    history = (payload.get("history") or "").strip()
    return bool(psych and len(psych) >= 50 and plus_val and minus_val and history and len(history) >= 50)


async def enrich_card(card: AromaCardModel, session) -> bool:
    """Enrich a single card via Claude. Returns True if updated."""
    from bot.services.claude_client import call_claude

    prompt = _build_prompt(card)
    log.info("  Calling Claude for %s ...", card.slug)

    response_text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        context=f"enrich_psychological:{card.slug}",
    )

    # Parse JSON response
    # Strip potential markdown fences
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.error("  FAIL %s: invalid JSON from Claude: %s\n%s", card.slug, exc, text[:200])
        return False

    # Validate required fields
    psych = (data.get("psychological_properties") or "").strip()
    rv = data.get("resource_values") or {}
    plus_val = (rv.get("plus") or "").strip()
    minus_val = (rv.get("minus") or "").strip()
    history = (data.get("history") or "").strip()

    if not psych or not plus_val or not minus_val or not history:
        log.error("  FAIL %s: incomplete response from Claude", card.slug)
        return False

    # Update payload
    payload = dict(card.payload or {})
    payload["psychological_properties"] = psych
    payload["resource_values"] = {"plus": plus_val, "minus": minus_val}
    payload["history"] = history
    card.payload = payload

    log.info("  OK   %s: psych=%d chars, plus=%d, minus=%d, history=%d",
             card.slug, len(psych), len(plus_val), len(minus_val), len(history))
    return True


async def main() -> None:
    force = "--force" in sys.argv
    target_slug = None
    for arg in sys.argv[1:]:
        if arg.startswith("--slug="):
            target_slug = arg.split("=", 1)[1]

    slugs = [target_slug] if target_slug else PDF_IMPORT_SLUGS

    updated = 0
    skipped = 0
    failed = 0

    async with AsyncSessionLocal() as session:
        for slug in slugs:
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == slug)
            )
            card = result.scalar_one_or_none()
            if not card:
                log.warning("  SKIP %s: card not found in DB", slug)
                skipped += 1
                continue

            if _is_populated(card) and not force:
                log.info("  SKIP %s: already populated", slug)
                skipped += 1
                continue

            try:
                if await enrich_card(card, session):
                    updated += 1
                else:
                    failed += 1
            except Exception as exc:
                log.error("  FAIL %s: %s", slug, exc)
                failed += 1

        if updated > 0:
            await session.commit()
            log.info("Committed %d updates", updated)

    log.info("Done: %d updated, %d skipped, %d failed", updated, skipped, failed)


if __name__ == "__main__":
    asyncio.run(main())
