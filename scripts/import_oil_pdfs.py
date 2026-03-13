"""Import essential oil PDFs from data/oil_pdfs/ into the AromaCard KB.

Usage:
    .venv/bin/python scripts/import_oil_pdfs.py [--dry-run] [--file ЛАВАНДА.pdf]

Options:
    --dry-run   Print what would be imported; do not write to DB.
    --file      Process only this specific filename (with or without .pdf).
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

PDF_DIR = ROOT / "data" / "oil_pdfs"

# RU filename stem → (slug, source_type, aliases)
OIL_SPECS: dict[str, dict] = {
    "АПЕЛЬСИН":         {"slug": "orange",            "source_type": "citrus",  "aliases": []},
    "БАЗИЛИК":          {"slug": "basil",             "source_type": "herb",    "aliases": []},
    "БЕРГАМОТ":         {"slug": "bergamot",          "source_type": "citrus",  "aliases": []},
    "ВЕТИВЕР":          {"slug": "vetiver",           "source_type": "grass",   "aliases": []},
    "ГВОЗДИКА":         {"slug": "clove",             "source_type": "spice",   "aliases": []},
    "ГЕРАНЬ":           {"slug": "geranium",          "source_type": "flower",  "aliases": []},
    "ЖАСМИН":           {"slug": "jasmine",           "source_type": "flower",  "aliases": []},
    "ИЛАНГ-ИЛАНГ":      {"slug": "ylang-ylang",       "source_type": "flower",  "aliases": ["Иланг"]},
    "ИМБИРЬ":           {"slug": "ginger",            "source_type": "spice",   "aliases": []},
    "КЕДР":             {"slug": "cedarwood",         "source_type": "tree",    "aliases": ["Кедр атласский"]},
    "КИПАРИС":          {"slug": "cypress",           "source_type": "tree",    "aliases": []},
    "КОРИЦА":           {"slug": "cinnamon",          "source_type": "spice",   "aliases": []},
    "ЛАВАНДА":          {"slug": "lavender",          "source_type": "flower",  "aliases": []},
    "ЛАДАН":            {"slug": "frankincense",      "source_type": "resin",   "aliases": ["Ладан Священный"]},
    "ЛЕМОНГРАСС":       {"slug": "lemongrass",        "source_type": "grass",   "aliases": []},
    "ЛИМОН":            {"slug": "lemon",             "source_type": "citrus",  "aliases": []},
    "МАНДАРИН":         {"slug": "mandarin",          "source_type": "citrus",  "aliases": []},
    "МОЖЖЕВЕЛЬНИК":     {"slug": "juniper",           "source_type": "tree",    "aliases": []},
    "МЯТА ПЕРЕЧНАЯ":    {"slug": "peppermint",        "source_type": "herb",    "aliases": ["Мята"]},
    "НЕРОЛИ":           {"slug": "neroli",            "source_type": "flower",  "aliases": []},
    "ПАЧУЛИ":           {"slug": "patchouli",         "source_type": "herb",    "aliases": []},
    "РОЗА":             {"slug": "rose",              "source_type": "flower",  "aliases": []},
    "РОЗМАРИН":         {"slug": "rosemary",          "source_type": "herb",    "aliases": []},
    "РОМАШКА ГЕРМАНСКАЯ": {"slug": "german-chamomile","source_type": "flower",  "aliases": ["Ромашка немецкая"]},
    "САНДАЛ":           {"slug": "sandalwood",        "source_type": "tree",    "aliases": []},
    "ТИМЬЯН":           {"slug": "thyme",             "source_type": "herb",    "aliases": []},
    "ФЕНХЕЛЬ":          {"slug": "fennel",            "source_type": "herb",    "aliases": []},
    "ЭВКАЛИПТ":         {"slug": "eucalyptus-globulus","source_type": "tree",   "aliases": ["Эвкалипт"]},
}

_PARSE_PROMPT = """\
Ниже текст, извлечённый из PDF-карточки эфирного масла.
Верни JSON-объект со следующими полями (строки, пустая строка если нет данных):
- name: название масла на русском
- description: краткое описание (1-3 предложения)
- therapeutic_properties: терапевтические свойства
- psychological_properties: психологические свойства / эмоциональное действие
- botanical_family: ботаническое семейство
- extraction_method: способ получения
- contraindications: противопоказания
- origin_countries: страны происхождения
- key: ключевая фраза или ключ масла (1 строка)
- volatility: летучесть (top/middle/base или описание)

Верни ТОЛЬКО JSON без обёрток. Текст карточки:
{text}
"""


def _extract_text_pdfplumber(path: Path) -> str:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            pages = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
            return "\n".join(pages)
    except Exception as exc:
        print(f"  pdfplumber failed ({exc}), trying pypdf fallback")
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as exc2:
            print(f"  pypdf also failed: {exc2}")
            return ""


def _parse_with_claude(text: str, api_key: str) -> dict:
    """Send PDF text to Claude Haiku and get structured fields back."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    truncated = text[:6000]  # stay within token budget
    prompt = _PARSE_PROMPT.format(text=truncated)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    # Strip markdown code block if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


async def _upsert_card(slug: str, name: str, source_type: str, aliases: list[str], payload: dict) -> str:
    """Upsert an AromaCardModel entry. Returns 'created' or 'updated'."""
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == slug)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            card = AromaCardModel(
                slug=slug,
                name=name,
                source_type=source_type,
                category="aroma",
                aliases=aliases,
                payload=payload,
            )
            session.add(card)
            action = "created"
        else:
            existing.name = name
            existing.source_type = source_type
            existing.aliases = aliases
            existing.payload = {**existing.payload, **payload}
            action = "updated"
        await session.commit()
    return action


def _discover_pdfs(only_file: str | None = None) -> list[tuple[Path, dict]]:
    """Return list of (pdf_path, spec) for all known PDFs in data/oil_pdfs/."""
    results = []
    for stem, spec in OIL_SPECS.items():
        filename = f"{stem}.pdf"
        if only_file and only_file.rstrip(".pdf").upper() not in (stem, stem.upper()):
            # also check exact match with extension
            if only_file.upper() not in (filename.upper(), stem.upper()):
                continue
        path = PDF_DIR / filename
        if path.exists():
            results.append((path, spec))
        else:
            print(f"  WARNING: expected PDF not found: {path}")
    return results


async def run(dry_run: bool = False, only_file: str | None = None) -> list[str]:
    """Main import routine. Returns list of processed slugs."""
    from config import settings

    entries = _discover_pdfs(only_file)
    if not entries:
        print("No PDFs found to process.")
        return []

    api_key = getattr(settings, "anthropic_api_key", None) or ""
    processed: list[str] = []

    for pdf_path, spec in entries:
        slug = spec["slug"]
        stem = pdf_path.stem
        print(f"Processing {stem} → {slug} ...", end=" ", flush=True)

        text = _extract_text_pdfplumber(pdf_path)
        if not text.strip():
            print("SKIP (empty text)")
            continue

        try:
            fields = _parse_with_claude(text, api_key)
        except Exception as exc:
            print(f"SKIP (Claude error: {exc})")
            continue

        name = fields.get("name") or stem
        payload = {
            "description":             fields.get("description", ""),
            "key":                     fields.get("key", ""),
            "therapeutic_properties":  fields.get("therapeutic_properties", ""),
            "psychological_properties":fields.get("psychological_properties", ""),
            "botanical_family":        fields.get("botanical_family", ""),
            "extraction_method":       fields.get("extraction_method", ""),
            "contraindications":       fields.get("contraindications", ""),
            "origin_countries":        fields.get("origin_countries", ""),
            "volatility":              fields.get("volatility", ""),
            "source": "pdf_import",
        }

        if dry_run:
            print(f"DRY-RUN → would upsert '{name}' ({slug})")
            processed.append(slug)
            continue

        action = await _upsert_card(
            slug=slug,
            name=name,
            source_type=spec["source_type"],
            aliases=spec["aliases"],
            payload=payload,
        )
        print(action)
        processed.append(slug)

    print(f"\nDone: {len(processed)}/{len(entries)} oils processed.")
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Import essential oil PDFs into AromaCard KB")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--file", default=None, help="Process only this file (e.g. ЛАВАНДА or ЛАВАНДА.pdf)")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, only_file=args.file))


if __name__ == "__main__":
    main()
