#!/usr/bin/env python3
"""Parse all «Смесь от/для …» recipes from data/oil_pdfs/handbook_parts/base.pdf.

Produces data/base_blends.json in the same format expected by upsert_cards().

Usage:
    .venv/bin/python scripts/parse_base_blends.py --dry-run   # preview
    .venv/bin/python scripts/parse_base_blends.py              # save JSON
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "data" / "oil_pdfs" / "handbook_parts" / "base.pdf"
OUT_PATH = ROOT / "data" / "base_blends.json"

# ── Transliteration ──────────────────────────────────────────────────────────

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify_ru(text: str) -> str:
    """Transliterate Russian text into a kebab-case slug."""
    text = text.lower().replace("№", "").replace("ё", "е")
    result = "".join(TRANSLIT.get(c, c) for c in text)
    return re.sub(r"[^a-z0-9]+", "-", result).strip("-")


def slugify_en(text: str) -> str:
    """English name → kebab-case slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ── Ingredient parsing ────────────────────────────────────────────────────────

# Matches: "N капель/капли/капля Русское имя (English Name)"
# Bullet can be: •, ✓, z, у, s, -, – , *, digit+dot, or nothing
# Finds ALL "N капель OilName (EnglishName)" occurrences in a line.
# Uses findall to handle two-column layouts where a single line has multiple ingredients.
_INGR_FINDALL_RE = re.compile(
    r"(\d{1,3})\s*"                              # group 1: drops
    r"кап(?:л[иеёь]|ель)?\s+"                    # "капли/капель/капля"
    r"((?:[А-Яа-яЁёA-Za-z][\wА-Яа-яЁё .'-]*)"  # group 2: oil name start
    r"(?:\s*\([^)]+\))?)",                        # optional (English) in parens
    re.IGNORECASE,
)

# Parse "Русское имя (English Name)" from captured oil name
_NAME_RE = re.compile(
    r"^(.+?)\s*\(([^)]+)\)\s*$"
)

# Noise to strip from captured names
_NOISE_RE = re.compile(
    r"\s*(?:Для разведения|Смешайте|Применяйте|можно наносить|Втирайте|"
    r"Медленно|Смешать|или основы|Перемешайте|в чистом|на область|"
    r"Принимайте|разбавленн|в сочетании).*$",
    re.IGNORECASE,
)


def _parse_name(raw: str) -> tuple[str, str]:
    """Split 'Русское имя (English Name)' → (name_ru, name_en)."""
    cleaned = _NOISE_RE.sub("", raw).rstrip(" .,;:!?")
    m = _NAME_RE.match(cleaned)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return cleaned.strip(), ""


def _extract_ingredients_from_lines(lines: list[str]) -> list[dict]:
    """Extract all ingredients from a block of text lines using findall."""
    ingredients: list[dict] = []
    for line in lines:
        for m in _INGR_FINDALL_RE.finditer(line):
            drops = int(m.group(1))
            name_ru, name_en = _parse_name(m.group(2))
            if not name_ru or len(name_ru) < 2:
                continue
            ingredients.append({"drops": drops, "name_ru": name_ru, "name_en": name_en})
    return ingredients


# ── Blend header detection ────────────────────────────────────────────────────

_HEADER_RE = re.compile(
    r"((?:Общая|Женская)\s+)?"
    r"[Сс]месь\s+"
    r"(?:от|для|при|для\s+ополаскивания)\s+"
    r"(.+?)$"
)

# Lines that START with a blend header (not mentions in running text)
_LINE_START_RE = re.compile(
    r"^((?:Общая|Женская)\s+)?[Сс]месь\s+(?:от|для|при)"
)

# Stop markers — next section
_STOP_RE = re.compile(
    r"^(СПОСОБЫ ПРИМЕНЕНИЯ|Ингаляция|Локально|Прием внутрь|РЕКОМЕНДАЦИИ|"
    r"[А-ЯЁABCDEFGHIJKLMNOPQRSTUVWXYZ]{3,}\s|см\.\s)",
    re.IGNORECASE,
)


def _split_multi_headers(line: str) -> list[str]:
    """Split a line that contains multiple blend headers side by side.

    Example: 'Смесь от ушибов №1 Смесь от ушибов №2'
    → ['Смесь от ушибов №1', 'Смесь от ушибов №2']
    """
    # Find all positions where 'Смесь' starts
    positions = [m.start() for m in re.finditer(r"(?:Общая |Женская )?[Сс]месь\s+(?:от|для|при)", line)]
    if len(positions) <= 1:
        return [line.strip()]

    headers = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(line)
        headers.append(line[pos:end].strip())
    return headers


def _clean_blend_name(raw: str) -> str:
    """Clean up a blend header name."""
    # Remove trailing ingredient fragments that may have been merged
    name = re.sub(r"\s*[✓z•у]\s*\d+\s*кап.*$", "", raw, flags=re.IGNORECASE)
    # Remove trailing page numbers
    name = re.sub(r"\s+\d{2,3}\s*$", "", name)
    # Normalize whitespace
    name = " ".join(name.split())
    return name.strip()


# ── Category group heuristic ─────────────────────────────────────────────────

_CATEGORY_MAP = {
    "кожа|морщин|угр|акне|псориаз|лишай|шрам|целлюлит|печеноч.*пятн|склеродерм|фурункул|сухой кожи|жирной кожи|перхот": "beauty",
    "волос|ногт|кожи головы": "beauty",
    "головн|мигрен|боли в|ушиб|растяж|мозол|шишк|тендинит|мышц|спине|стопа|подагр|стоп": "pain",
    "горл|фарингит|бронхит|кашл|пневмон|синусит|нос|простуд|гриппа": "respiratory",
    "геморро|диарея|дивертикул|дизентери|колит|изжог|кислот": "digestion",
    "аневризм|варикоз|флебит|холестерин|отек": "cardiovascular",
    "бессоница|памят|паралич|невропат|нерв|кистевого|PC|аутизм|БАС": "nervous",
    "волчанк|герпес|опоясыва|мононуклеоз|кори|полиомиелит|кандид|грибк|дрожжев|бактери|паразит": "immune",
    "менструа|кист|груди|предстат|вагинал": "hormonal",
    "укус|пчел|паук|скорпион|клоп|насеком|отпугив": "first_aid",
    "психолог|травм": "emotional",
    "печен|лимфат": "detox",
    "омолож|упруг": "beauty",
}


def _guess_category_group(name: str) -> str:
    name_lower = name.lower()
    for pattern, group in _CATEGORY_MAP.items():
        if re.search(pattern, name_lower):
            return group
    return "health"


# ── Description generation ────────────────────────────────────────────────────

def _generate_description(name: str, ingredients: list[dict]) -> str:
    """Generate a meaningful description based on blend name and ingredients."""
    # Map condition from blend name
    condition_match = re.search(r"[Сс]месь\s+(?:от|для|при)\s+(.+?)(?:\s*№\s*\d+)?$", name)
    condition = condition_match.group(1).strip() if condition_match else ""

    oil_names_ru = [ing["name_ru"] for ing in ingredients if ing["name_ru"]]
    oil_names_en = [ing["name_en"] for ing in ingredients if ing["name_en"]]

    if not oil_names_ru and not oil_names_en:
        return f"Рецептурная смесь эфирных масел, рекомендованная при: {condition}." if condition else ""

    oils_list = ", ".join(oil_names_ru[:4]) if oil_names_ru else ", ".join(oil_names_en[:4])
    extra = f" и др. ({len(ingredients)} масел)" if len(ingredients) > 4 else f" ({len(ingredients)} масел)"

    condition_text = f" при {condition}" if condition else ""

    return (
        f"Терапевтическая смесь эфирных масел{condition_text}. "
        f"Состав: {oils_list}{extra}. "
        f"Рецепт из справочника Essential Oils Desk Reference."
    )


def _generate_name_en(name: str) -> str:
    """Generate English name from Russian blend name."""
    # Simple mapping for common conditions
    m = re.search(r"[Сс]месь\s+(от|для|при)\s+(.+?)(?:\s*№\s*(\d+))?(?:\s*\((.+?)\))?$", name)
    if not m:
        return ""
    variant = f" No.{m.group(3)}" if m.group(3) else ""
    note = f" ({m.group(4)})" if m.group(4) else ""
    # We can't reliably translate, so leave name_en minimal
    return f"Blend{variant}{note}" if variant or note else ""


# ── Main parsing ──────────────────────────────────────────────────────────────

_FALSE_POSITIVE_KW = [
    "используйте эту смесь", "вышеупомянутую смесь",
    "наносите смесь", "возьмите смесь", "добавьте смесь",
    "перемешайте вышеупомянутую", "чередуя смесь",
    "используя вышеупомянутую смесь", "используя следующую смесь",
    "эта удивительна смесь", "эта смесь для",
    "накапать в диффузор",
    "обладает частотой",
    "помощи, то эта удивительна",
]


def _collect_ingredient_block(all_lines: list[tuple[int, str]], start_idx: int, max_lines: int = 20) -> list[str]:
    """Collect ingredient lines from start_idx until a stop marker."""
    lines: list[str] = []
    for j in range(start_idx, min(start_idx + max_lines, len(all_lines))):
        _, ln = all_lines[j]
        stripped = ln.strip()
        if not stripped:
            continue
        # Stop at usage / new section — unless line itself has ingredient data
        if _STOP_RE.match(stripped) and not re.search(r"\d+\s*кап", stripped):
            break
        if re.match(r"^[А-ЯЁ\s]{10,}$", stripped):
            break
        # Stop if we hit a new blend header (different blend)
        if _LINE_START_RE.match(stripped):
            break
        lines.append(stripped)
    return lines


def _build_card(
    name: str, ingredients: list[dict], seen_slugs: set[str],
) -> dict | None:
    """Build a card dict from parsed name + ingredients."""
    if not ingredients:
        return None

    # Generate slug
    condition_match = re.search(
        r"(?:Общая |Женская )?[Сс]месь\s+(?:от|для|при)\s+(.+?)$", name,
    )
    condition = condition_match.group(1).strip() if condition_match else name
    variant_match = re.search(r"№\s*(\d+)", condition)
    variant = variant_match.group(1) if variant_match else ""
    condition_clean = re.sub(r"\s*№\s*\d+.*$", "", condition).strip()
    condition_clean = re.sub(r"\s*\(.*?\)\s*$", "", condition_clean).strip()

    slug_base = f"smesh-ot-{slugify_ru(condition_clean)}"
    slug = f"{slug_base}-{variant}" if variant else slug_base

    if slug in seen_slugs:
        for n in range(2, 10):
            candidate = f"{slug_base}-{n}"
            if candidate not in seen_slugs:
                slug = candidate
                break
    seen_slugs.add(slug)

    ing_names = [ing["name_en"] or ing["name_ru"] for ing in ingredients]
    ing_drops = [ing["drops"] for ing in ingredients]
    ing_slugs = [
        slugify_en(ing["name_en"]) if ing["name_en"] else slugify_ru(ing["name_ru"])
        for ing in ingredients
    ]
    ing_names_ru = [ing["name_ru"] for ing in ingredients]

    return {
        "slug": slug,
        "name": name,
        "category": "blend",
        "source_type": "blend",
        "aliases": [],
        "payload": {
            "name_ru": name,
            "name_en": _generate_name_en(name),
            "description": _generate_description(name, ingredients),
            "ingredient_names": ing_names,
            "ingredient_drops": ing_drops,
            "ingredient_slugs": ing_slugs,
            "ingredient_names_ru": ing_names_ru,
            "blend_category": "",
            "category_group": _guess_category_group(name),
            "source_pdf": "base",
        },
    }


def parse_blends(dry_run: bool = False) -> list[dict]:
    """Parse all blend recipes from base.pdf."""
    import pdfplumber

    pdf = pdfplumber.open(str(PDF_PATH))

    # Collect all text with page numbers
    all_lines: list[tuple[int, str]] = []  # (page_num, line)
    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if not text:
            continue
        for line in text.split("\n"):
            all_lines.append((i + 1, line))

    # Pass 1: find blend header lines and group multi-headers
    # Each entry: (line_idx, page, [name1, name2, ...])
    header_groups: list[tuple[int, int, list[str]]] = []
    seen_line_idxs: set[int] = set()

    for idx, (pg, line) in enumerate(all_lines):
        if idx in seen_line_idxs:
            continue
        stripped = line.strip()
        if not _LINE_START_RE.match(stripped):
            continue
        if any(kw in stripped.lower() for kw in _FALSE_POSITIVE_KW):
            continue
        headers = _split_multi_headers(stripped)
        names = [_clean_blend_name(h) for h in headers]
        names = [n for n in names if len(n) >= 8]
        if names:
            header_groups.append((idx, pg, names))
            seen_line_idxs.add(idx)

    print(f"Found {len(header_groups)} header lines ({sum(len(g[2]) for g in header_groups)} blend names)")

    # Pass 2: for each header group, collect ingredient lines and assign to blends
    blends: list[dict] = []
    seen_slugs: set[str] = set()

    for g_idx, (line_idx, page, names) in enumerate(header_groups):
        # End boundary: next header group line or +20 lines
        next_line_idx = (
            header_groups[g_idx + 1][0]
            if g_idx + 1 < len(header_groups)
            else len(all_lines)
        )

        # Collect ingredient lines from after the header
        ingredient_lines = _collect_ingredient_block(
            all_lines, line_idx + 1, max_lines=min(20, next_line_idx - line_idx - 1),
        )

        # Also check if header line itself has ingredients embedded
        header_text = all_lines[line_idx][1]
        header_tail = re.sub(
            r"^.*?[Сс]месь\s+(?:от|для|при)\s+\S+.*?(?=\s*[✓z•у\-]\s*\d|\s*\d+\s*кап|$)",
            "", header_text,
        )
        if header_tail.strip() and re.search(r"\d+\s*кап", header_tail):
            ingredient_lines.insert(0, header_tail.strip())

        all_ingredients = _extract_ingredients_from_lines(ingredient_lines)

        if len(names) == 1:
            # Single blend — straightforward
            card = _build_card(names[0], all_ingredients, seen_slugs)
            if card:
                blends.append(card)
            elif dry_run:
                print(f"  SKIP (no ingredients): p.{page} {names[0]}")
        elif len(names) == 2:
            # Two-column layout: ingredients are interleaved (left, right, left, right)
            left_ings = all_ingredients[0::2]
            right_ings = all_ingredients[1::2]
            card1 = _build_card(names[0], left_ings, seen_slugs)
            card2 = _build_card(names[1], right_ings, seen_slugs)
            if card1:
                blends.append(card1)
            elif dry_run:
                print(f"  SKIP (no ingredients): p.{page} {names[0]}")
            if card2:
                blends.append(card2)
            elif dry_run:
                print(f"  SKIP (no ingredients): p.{page} {names[1]}")
        else:
            # 3+ columns (rare) — assign sequentially by column count
            n_cols = len(names)
            for col, nm in enumerate(names):
                col_ings = all_ingredients[col::n_cols]
                card = _build_card(nm, col_ings, seen_slugs)
                if card:
                    blends.append(card)
                elif dry_run:
                    print(f"  SKIP (no ingredients): p.{page} {nm}")

    return blends


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Parse blend recipes from base.pdf")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    blends = parse_blends(dry_run=args.dry_run)

    print(f"\nParsed {len(blends)} blends with ingredients")

    if args.dry_run:
        # Show sample
        for b in blends[:5]:
            p = b["payload"]
            print(f"\n  {b['slug']}:")
            print(f"    name: {b['name']}")
            print(f"    description: {p['description'][:120]}...")
            ings = list(zip(p["ingredient_drops"], p["ingredient_names"], p["ingredient_names_ru"]))
            for drops, en, ru in ings:
                print(f"      {drops} кап — {ru} ({en})")
            print(f"    category_group: {p['category_group']}")

        # Stats
        groups: dict[str, int] = {}
        for b in blends:
            g = b["payload"]["category_group"]
            groups[g] = groups.get(g, 0) + 1
        print("\nCategory groups:")
        for g, cnt in sorted(groups.items(), key=lambda x: -x[1]):
            print(f"  {g}: {cnt}")

        # Description quality check
        short_descs = [b for b in blends if len(b["payload"]["description"]) < 60]
        if short_descs:
            print(f"\nWARNING: {len(short_descs)} blends have short descriptions (<60 chars):")
            for b in short_descs[:5]:
                print(f"  {b['slug']}: {b['payload']['description']!r}")
    else:
        OUT_PATH.write_text(json.dumps(blends, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
