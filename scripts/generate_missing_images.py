"""Generate Gemini images for reference cards that only have SVG placeholders.

Usage:
    .venv/bin/python scripts/generate_missing_images.py [--dry-run] [--category aroma] [--slug lavender]

Options:
    --dry-run           Print cards that need images; do not generate or write.
    --category          Limit to one category (aroma, blend, practice, concept, symptom).
    --slug              Limit to one specific card slug.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IMAGES_DIR = ROOT / "assets" / "reference_images"
SVG_PREFIX = "data:image/svg+xml"


def _is_placeholder(image_url: str | None) -> bool:
    """Return True if image_url is an SVG placeholder or empty."""
    if not image_url:
        return True
    return str(image_url).startswith(SVG_PREFIX)


def _image_save_path(category: str, slug: str) -> Path:
    """Canonical path where generated images are saved."""
    return IMAGES_DIR / f"{category}s" / f"{slug}.jpg"


async def _audit_cards(category: str | None = None) -> list[dict]:
    """Return list of cards that have only SVG placeholder images."""
    from bot.services.miniapp_references import _serialize_model
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    await _ensure_seeded()
    async with AsyncSessionLocal() as session:
        query = select(AromaCardModel)
        if category:
            query = query.where(AromaCardModel.category == category)
        result = await session.execute(query)
        models = result.scalars().all()

    cards = []
    for model in models:
        serialized = _serialize_model(model)
        image_url = serialized.get("image_url", "")
        if _is_placeholder(image_url):
            cards.append({
                "slug": model.slug,
                "name": model.name,
                "category": model.category,
                "source_type": model.source_type,
                "description": str((model.payload or {}).get("description_short") or (model.payload or {}).get("description") or "")[:200],
            })
    return cards


async def _ensure_seeded() -> None:
    from bot.services.miniapp_references import seed_reference_cards_if_empty
    await seed_reference_cards_if_empty()


_CATEGORY_PROMPTS = {
    "aroma": (
        "Create a beautiful botanical illustration of the plant '{name}'. "
        "{description}. "
        "Style: soft watercolor botanical illustration, muted natural colors, clean white background. "
    ),
    "symptom": (
        "Create a gentle, conceptual medical illustration representing '{name}'. "
        "{description}. "
        "Style: soft, calming, abstract medical/anatomical illustration. Muted tones, no text. "
        "Focus on the body system or concept, not herbs or plants. "
    ),
    "blend": (
        "Create an illustration representing the purpose of an aromatherapy blend called '{name}'. "
        "{description}. "
        "Style: warm, inviting illustration showing the blend's therapeutic goal (e.g. relaxation, immunity, beauty). "
        "Muted natural colors, no text. "
    ),
    "practice": (
        "Create a serene illustration of a meditative or therapeutic practice: '{name}'. "
        "{description}. "
        "Style: peaceful, contemplative scene with soft lighting and calming colors. No text. "
    ),
}


def _generate_image(name: str, description: str, category: str = "aroma") -> bytes | None:
    """Generate an image via NanoBanana API. Returns raw bytes or None."""
    from bot.services.gemini_images import generate_gemini_image_sync

    template = _CATEGORY_PROMPTS.get(category, _CATEGORY_PROMPTS["aroma"])
    prompt = template.format(name=name, description=description) + "No text overlays. Square format."
    return generate_gemini_image_sync(prompt, log_context=f"missing-img:{name}")


async def _upsert_image_url(slug: str, image_url: str) -> None:
    """Update card payload with new image_url."""
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == slug)
        )
        card = result.scalar_one_or_none()
        if card is None:
            return
        card.payload = {**card.payload, "image_url": image_url}
        await session.commit()


async def run(
    dry_run: bool = False,
    category: str | None = None,
    slug: str | None = None,
) -> list[str]:
    """Main routine. Returns list of slugs that were (or would be) processed."""
    from config import settings

    cards = await _audit_cards(category)

    # Filter to specific slug if requested
    if slug:
        cards = [c for c in cards if c["slug"] == slug]

    if not cards:
        print("No cards with placeholder images found.")
        return []

    print(f"Found {len(cards)} card(s) with placeholder images.")

    if dry_run:
        for card in cards:
            print(f"  DRY-RUN: {card['slug']} ({card['category']}) — {card['name']}")
        return [c["slug"] for c in cards]

    if not settings.image_api_key:
        print("ERROR: NANA_BANANA_API_KEY not configured. Use --dry-run to audit only.")
        return []

    processed = []
    for i, card in enumerate(cards):
        slug_val = card["slug"]
        cat = card["category"]
        name = card["name"]
        desc = card["description"]
        print(f"  [{i+1}/{len(cards)}] Generating image for {slug_val} ({name})...", end=" ", flush=True)

        img_bytes = _generate_image(name, desc, category=cat)
        if not img_bytes:
            print("SKIP (generation failed)")
            time.sleep(15)  # back off before next attempt
            continue

        save_path = _image_save_path(cat, slug_val)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(img_bytes)

        image_url = f"/reference-images/{cat}s/{slug_val}.jpg"
        await _upsert_image_url(slug_val, image_url)
        try:
            display_path = save_path.relative_to(ROOT)
        except ValueError:
            display_path = save_path
        print(f"saved → {display_path}")
        processed.append(slug_val)
        time.sleep(10)  # ~6 req/min to stay within free tier limits

    print(f"\nDone: {len(processed)}/{len(cards)} images generated.")
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Gemini images for reference cards")
    parser.add_argument("--dry-run", action="store_true", help="Audit only, no generation")
    parser.add_argument("--category", default=None, help="Filter by category (aroma, blend, etc.)")
    parser.add_argument("--slug", default=None, help="Process only this slug")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, category=args.category, slug=args.slug))


if __name__ == "__main__":
    main()
