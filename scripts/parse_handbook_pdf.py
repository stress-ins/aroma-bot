"""
Parse /tmp/pdf_text.txt into 4 JSON files:
  data/pdf_oils_patch.json   — new payload fields for existing 43 oils
  data/pdf_oils_new.json     — ~37 new individual oil cards
  data/pdf_blends.json       — ~100 blend cards
  data/pdf_symptoms.json     — symptom cards

Run:
    python scripts/parse_handbook_pdf.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

PDF_TEXT = Path("/tmp/pdf_text.txt")
OUT_DIR = Path(__file__).parent.parent / "data"

# ── existing slug mapping ────────────────────────────────────────────────────
EXISTING_SLUG_BY_EN_NAME: dict[str, str] = {
    "angelica": "angelica",
    "balsam fir idaho": "balsam-fir",
    "balsam fir": "balsam-fir",
    "basil": "basil",
    "bergamot": "bergamot",
    "black pepper": "black-pepper",
    "blue spruce": "blue-spruce",
    "idaho blue spruce": "blue-spruce",
    "cassia": "cassia",
    "cedarwood": "cedarwood",
    "cinnamon bark": "cinnamon",
    "cinnamon": "cinnamon",
    "citronella": "citronella",
    "clary sage": "clary-sage",
    "clove": "clove",
    "copaiba": "copaiba",
    "cypress": "cypress",
    "eucalyptus globulus": "eucalyptus-globulus",
    "eucalyptus": "eucalyptus-globulus",
    "fennel": "fennel",
    "frankincense": "frankincense",
    "geranium": "geranium",
    "german chamomile": "german-chamomile",
    "ginger": "ginger",
    "grapefruit": "grapefruit",
    "helichrysum": "helichrysum",
    "jasmine": "jasmine",
    "juniper": "juniper",
    "kunzea": "kunzea",
    "lavender": "lavender",
    "lemon": "lemon",
    "lemongrass": "lemongrass",
    "lime": "lime",
    "mandarin": "mandarin",
    "marjoram": "marjoram",
    "neroli": "neroli",
    "orange": "orange",
    "oregano": "oregano",
    "patchouli": "patchouli",
    "peppermint": "peppermint",
    "rose": "rose",
    "rosemary": "rosemary",
    "sandalwood": "sandalwood",
    "spruce": "spruce",
    "tea tree": "tea-tree",
    "thyme": "thyme",
    "vetiver": "vetiver",
    "ylang ylang": "ylang-ylang",
    "ylang-ylang": "ylang-ylang",
    "black spruce": "black-spruce",
}

# Map Russian oil names → English slug for cross-ref resolution
RU_TO_SLUG: dict[str, str] = {
    "ангелика": "angelica",
    "дягиль": "angelica",
    "базилик": "basil",
    "бергамот": "bergamot",
    "черный перец": "black-pepper",
    "черная ель": "black-spruce",
    "голубая ель": "blue-spruce",
    "кассия": "cassia",
    "кедр": "cedarwood",
    "кедровое дерево": "cedarwood",
    "корица": "cinnamon",
    "цитронелла": "citronella",
    "мускатный шалфей": "clary-sage",
    "шалфей мускатный": "clary-sage",
    "гвоздика": "clove",
    "копаиба": "copaiba",
    "кипарис": "cypress",
    "укроп": "dill",
    "эвкалипт": "eucalyptus-globulus",
    "эвкалипт шаровидный": "eucalyptus-globulus",
    "фенхель": "fennel",
    "ладан": "frankincense",
    "герань": "geranium",
    "ромашка немецкая": "german-chamomile",
    "ромашка": "german-chamomile",
    "имбирь": "ginger",
    "грейпфрут": "grapefruit",
    "бессмертник": "helichrysum",
    "жасмин": "jasmine",
    "можжевельник": "juniper",
    "кунзея": "kunzea",
    "лаванда": "lavender",
    "лимон": "lemon",
    "лемонграсс": "lemongrass",
    "лайм": "lime",
    "мандарин": "mandarin",
    "майоран": "marjoram",
    "нероли": "neroli",
    "апельсин": "orange",
    "орегано": "oregano",
    "пачули": "patchouli",
    "мята перечная": "peppermint",
    "мята": "peppermint",
    "роза": "rose",
    "розмарин": "rosemary",
    "сандал": "sandalwood",
    "сандаловое дерево": "sandalwood",
    "ель": "spruce",
    "чайное дерево": "tea-tree",
    "тимьян": "thyme",
    "ветивер": "vetiver",
    "иланг-иланг": "ylang-ylang",
    "иланг иланг": "ylang-ylang",
    "пачули": "patchouli",
    "дубовый мох": "oakmoss",
    "мирра": "myrrh",
    "валериана": "valerian",
}


def slugify(text: str) -> str:
    """Convert English oil/blend name to slug."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def extract_article(text: str) -> str:
    """Find first article number like #3078 or #309708 in text."""
    m = re.search(r"#(\d{4,7})", text)
    return f"#{m.group(1)}" if m else ""


# ── Oil section parsing ──────────────────────────────────────────────────────
# Oil section runs from after the intro pages (~line 2340) to blends section
# Blends start with "СМЕСИ" heading

OIL_NAME_RE = re.compile(r"^([A-Z][A-Z &\-/()]+[A-Z])$")
# e.g. ANGELICA, BALSAM FIR IDAHO, TEA TREE, YLANG YLANG, BLACK PEPPER


BLEND_SECTION_HEADER = "СМЕСИ"
SYMPTOM_SECTION_HEADER = "ОБЩЕЕ СОСТОЯНИЕ ОРГАНИЗМА"


def find_section_start(lines: list[str], marker: str) -> int:
    for i, line in enumerate(lines):
        if line.strip() == marker:
            return i
    return -1


def split_comma_list(text: str) -> list[str]:
    """Split a comma/semicolon separated list of oil/blend names."""
    if not text:
        return []
    parts = re.split(r"[,;]+", text)
    result = []
    for p in parts:
        p = p.strip().strip("•").strip()
        # Remove trailing ™ and ® signs but keep the name
        p = re.sub(r"[™®]", "", p).strip()
        if p and len(p) > 1:
            result.append(p)
    return result


def extract_field_after(lines: list[str], start: int, end: int, marker: str) -> str:
    """Extract text on same line as marker and continuation lines until next marker."""
    result_lines = []
    in_section = False
    next_markers = [
        "Лечебные свойства",
        "При каких заболеваниях",
        "Духовное и эмоциональное",
        "Влияние на ум",
        "Влияние на здоровье",
        "Применение и дозировки",
        "Использование",
        "Состояние",
        "Способ получения",
        "Входит в состав",
        "Комплементарные масла",
        "Комплиментарные",
        "Меры предосторожности",
        "На какие системы",
        "Когда применять",
        "Состав:",
        "#",
    ]
    for i in range(start, min(end, len(lines))):
        line = lines[i].strip()
        if line.startswith(marker):
            in_section = True
            # Text after the colon on the same line
            after = line[len(marker):].lstrip(":").strip()
            if after:
                result_lines.append(after)
            continue
        if in_section:
            # Check if we've hit another major section
            if any(line.startswith(m) for m in next_markers) or OIL_NAME_RE.match(line):
                break
            if line:
                result_lines.append(line)
    return " ".join(result_lines)


def parse_oils(lines: list[str], oil_start: int, oil_end: int) -> list[dict]:
    """Parse individual oil entries between oil_start and oil_end."""
    entries = []
    i = oil_start

    while i < oil_end:
        line = lines[i].strip()
        if OIL_NAME_RE.match(line) and len(line) >= 3:
            en_name = line.strip()
            # Collect the block until the next OIL entry or blend section
            block_start = i
            block_end = i + 1
            while block_end < oil_end:
                next_line = lines[block_end].strip()
                if OIL_NAME_RE.match(next_line) and len(next_line) >= 3 and block_end > block_start + 5:
                    break
                block_end += 1

            block_lines = lines[block_start:block_end]
            block_text = " ".join(l.strip() for l in block_lines)

            # Article number
            article = extract_article(block_text)

            # Лечебные свойства
            lech = extract_field_after(block_lines, 0, len(block_lines), "Лечебные свойства")

            # При каких заболеваниях
            conditions = extract_field_after(block_lines, 0, len(block_lines), "При каких заболеваниях использовать")
            if not conditions:
                conditions = extract_field_after(block_lines, 0, len(block_lines), "Когда применять")

            # Применение и дозировки
            applications_lines = []
            in_app = False
            for bl in block_lines:
                stripped = bl.strip()
                if stripped.startswith("Применение и дозировки"):
                    in_app = True
                    after = stripped[len("Применение и дозировки"):].lstrip(":").strip()
                    if after:
                        applications_lines.append(after)
                    continue
                if in_app:
                    if any(stripped.startswith(m) for m in [
                        "Входит в состав", "Комплементарные", "Комплиментарные",
                        "Меры предосторожности", "Лечебные свойства",
                        "При каких заболеваниях", "Духовное и эмоциональное",
                    ]) or OIL_NAME_RE.match(stripped):
                        break
                    if stripped:
                        applications_lines.append(stripped)
            applications = "\n".join(applications_lines)

            # Входит в состав
            blends_raw = extract_field_after(block_lines, 0, len(block_lines), "Входит в состав")
            # also try alternate: "Входит в состав эфирных смесей"
            if not blends_raw:
                blends_raw = extract_field_after(block_lines, 0, len(block_lines), "Входит в состав эфирных")
            blends_containing = split_comma_list(blends_raw)

            # Комплементарные масла
            comp_raw = extract_field_after(block_lines, 0, len(block_lines), "Комплементарные масла")
            if not comp_raw:
                comp_raw = extract_field_after(block_lines, 0, len(block_lines), "Комплиментарные")
            complementary = split_comma_list(comp_raw)

            # Меры предосторожности
            prec_lines = []
            in_prec = False
            for bl in block_lines:
                stripped = bl.strip()
                if stripped.startswith("Меры предосторожности"):
                    in_prec = True
                    after = stripped[len("Меры предосторожности"):].lstrip(":").strip()
                    if after:
                        prec_lines.append(after)
                    continue
                if in_prec:
                    if any(stripped.startswith(m) for m in [
                        "Входит в состав", "Комплементарные", "Комплиментарные",
                        "Лечебные свойства", "При каких заболеваниях",
                        "Применение и дозировки",
                    ]) or (OIL_NAME_RE.match(stripped) and len(stripped) >= 3):
                        break
                    if stripped:
                        prec_lines.append(stripped)
            precautions = "\n".join(prec_lines)

            # Духовное и эмоциональное воздействие
            spiritual = extract_field_after(block_lines, 0, len(block_lines), "Духовное и эмоциональное воздействие")

            # Влияние на ум
            mind_effect = extract_field_after(block_lines, 0, len(block_lines), "Влияние на ум")

            # Влияние на здоровье
            health_effects = extract_field_after(block_lines, 0, len(block_lines), "Влияние на здоровье")

            # Способ получения
            extraction_method = extract_field_after(block_lines, 0, len(block_lines), "Способ получения")

            # Использование (synonym for applications in some PDF layouts)
            usage = extract_field_after(block_lines, 0, len(block_lines), "Использование")

            # Russian name — look for Ru characters after EN name
            ru_name = ""
            for bl in block_lines[1:8]:
                stripped = bl.strip()
                # Look for a line that is clearly Russian (has Cyrillic chars, not too long)
                if re.search(r"[а-яё]", stripped, re.I) and len(stripped) < 60:
                    if not any(stripped.startswith(m) for m in [
                        "Лечебные", "При каких", "Духовное", "Влияние",
                        "Применение", "Меры", "Входит", "Комплем", "Состав",
                        "Способ получения",
                    ]):
                        ru_name = stripped
                        break

            entry = {
                "name_en": en_name.title(),
                "name_ru": ru_name,
                "article_number": article,
                "therapeutic_properties": norm(lech),
                "conditions_for_use": norm(conditions),
                "applications": applications or norm(usage),
                "blends_containing_names": blends_containing,
                "complementary_oil_names": complementary,
                "precautions": norm(precautions),
                "spiritual_emotional": norm(spiritual),
                "mind_effect": norm(mind_effect),
                "health_effects": norm(health_effects),
                "extraction_method": norm(extraction_method),
            }
            entries.append(entry)
            i = block_end
        else:
            i += 1

    return entries


# ── Blend section parsing ────────────────────────────────────────────────────

def parse_blends(lines: list[str], blend_start: int, blend_end: int) -> list[dict]:
    """Parse blend entries."""
    entries = []
    i = blend_start

    while i < blend_end:
        line = lines[i].strip()
        if OIL_NAME_RE.match(line) and len(line) >= 3:
            en_name = line.strip()
            block_start = i
            block_end = i + 1
            while block_end < blend_end:
                next_line = lines[block_end].strip()
                if OIL_NAME_RE.match(next_line) and len(next_line) >= 3 and block_end > block_start + 5:
                    break
                block_end += 1

            block_lines = lines[block_start:block_end]
            block_text = " ".join(l.strip() for l in block_lines)

            article = extract_article(block_text)

            # Russian name
            ru_name = ""
            for bl in block_lines[1:6]:
                stripped = bl.strip()
                if re.search(r"[а-яё]", stripped, re.I) and len(stripped) < 60:
                    if not any(stripped.startswith(m) for m in [
                        "Лечебные", "При каких", "Духовное", "Влияние",
                        "Применение", "Меры", "Входит", "Комплем",
                        "Состав", "Разработана", "Создана", "Когда",
                    ]):
                        ru_name = stripped
                        break

            # Состав
            ingredients_raw = extract_field_after(block_lines, 0, len(block_lines), "Состав")
            ingredients = split_comma_list(ingredients_raw)

            # Description — text between EN name and first section header, skipping RU name
            desc_lines = []
            skipped_ru = False
            for bl in block_lines[1:]:
                stripped = bl.strip()
                if any(stripped.startswith(m) for m in [
                    "Состав", "Лечебные свойства", "При каких", "Когда применять",
                    "Применение", "Меры", "Духовное", "Влияние", "#",
                    "На какие системы",
                ]):
                    break
                if not stripped or OIL_NAME_RE.match(stripped):
                    continue
                # Skip the Russian name line (same as ru_name)
                if not skipped_ru and stripped == ru_name:
                    skipped_ru = True
                    continue
                desc_lines.append(stripped)
            description = " ".join(desc_lines[:8])  # limit to avoid noise

            # Therapeutic
            lech = extract_field_after(block_lines, 0, len(block_lines), "Лечебные свойства")

            # Conditions
            conditions = extract_field_after(block_lines, 0, len(block_lines), "При каких заболеваниях использовать")
            if not conditions:
                conditions = extract_field_after(block_lines, 0, len(block_lines), "Когда применять")

            # Applications
            app_lines = []
            in_app = False
            for bl in block_lines:
                stripped = bl.strip()
                if stripped.startswith("Применение и дозировки"):
                    in_app = True
                    after = stripped[len("Применение и дозировки"):].lstrip(":").strip()
                    if after:
                        app_lines.append(after)
                    continue
                if in_app:
                    if any(stripped.startswith(m) for m in [
                        "Входит в состав", "Комплементарные", "Комплиментарные",
                        "Меры предосторожности", "Лечебные свойства",
                        "При каких заболеваниях", "Духовное и эмоциональное",
                        "Состав",
                    ]) or (OIL_NAME_RE.match(stripped) and len(stripped) >= 3):
                        break
                    if stripped:
                        app_lines.append(stripped)
            applications = "\n".join(app_lines)

            # Complementary
            comp_raw = extract_field_after(block_lines, 0, len(block_lines), "Комплементарные масла")
            if not comp_raw:
                comp_raw = extract_field_after(block_lines, 0, len(block_lines), "Комплиментарные")
            complementary = split_comma_list(comp_raw)

            # Precautions
            prec_raw = extract_field_after(block_lines, 0, len(block_lines), "Меры предосторожности")
            precautions = norm(prec_raw)

            slug = slugify(en_name)

            entry = {
                "slug": f"blend-{slug}",
                "name": en_name.title(),
                "category": "blend",
                "source_type": "blend",
                "aliases": [ru_name] if ru_name else [],
                "payload": {
                    "article_number": article,
                    "name_ru": ru_name,
                    "name_en": en_name.title(),
                    "key": ru_name or en_name.title(),
                    "description": norm(description),
                    "therapeutic_properties": norm(lech),
                    "conditions_for_use": norm(conditions),
                    "applications": applications,
                    "ingredient_names": ingredients,
                    "complementary_oil_names": complementary,
                    "precautions": precautions,
                },
            }
            entries.append(entry)
            i = block_end
        else:
            i += 1

    return entries


# ── Symptom section parsing ─────────────────────────────────────────────────

# Symptom names can be ALL-CAPS or mixed-caps but start with uppercase Cyrillic
# They're followed within ~60 lines by "Одинарные:" or "Смеси:"
SYMPTOM_NAME_RE = re.compile(r"^[А-ЯЁ][А-ЯЁа-яёa-zA-Z0-9\s\-/(),\.«»–]{2,100}$")


def _extract_oil_name_from_token(token: str) -> str:
    """Extract clean English oil name from tokens like '4 Lavender (Лаванда),'."""
    # Remove leading garbage chars
    token = re.sub(r"^[4«»<>\s✓✔•\-–★☆◆◇■□▪▫]+", "", token).strip()
    # Strip trailing punctuation
    token = token.rstrip(",;.").strip()
    # Extract English part from "English (Russian)" pattern
    m = re.match(r"^(.+?)\s*\([^)]+\)\s*$", token)
    if m:
        return m.group(1).strip()
    return token


def _is_skip_line(line: str) -> bool:
    """Return True for lines that should be skipped in symptom parsing."""
    skip_prefixes = [
        "СПОСОБЫ ПРИМЕНЕНИЯ", "РЕКОМЕНД", "рЕК0МЕНд",
        "Питательные добавки", "Сыворотки", "Кремы", "Средства по уходу",
        "Ингаляция", "Локально", "Прием внутрь", "Распыл",
        "Нанести", "Наносите", "Добавьте", "Принимайте", "Смешайте",
        "Втирайте", "Вдыхайте", "Использ", "Капсул",
    ]
    return any(line.startswith(p) for p in skip_prefixes)


def _collect_oils_and_blends(lines: list[str], start: int, end: int) -> tuple[list[str], list[str]]:
    """Collect oil names and blend names from a block of lines."""
    oils: list[str] = []
    blends: list[str] = []
    mode = None  # "oils", "blends", None

    for idx in range(start, min(end, len(lines))):
        line = lines[idx].strip()
        if not line:
            continue

        # Mode switches
        if re.match(r"^Одинарные\s*:", line) or re.match(r"^Эфирные масла\s*:", line):
            mode = "oils"
            after = re.sub(r"^(Одинарные|Эфирные масла)\s*:\s*", "", line)
            if after:
                for tok in re.split(r",", after):
                    name = _extract_oil_name_from_token(tok)
                    if name and len(name) > 1:
                        oils.append(name)
            continue

        if re.match(r"^Смеси\s*:", line):
            mode = "blends"
            after = re.sub(r"^Смеси\s*:\s*", "", line)
            if after:
                for tok in re.split(r",", after):
                    name = _extract_oil_name_from_token(tok)
                    if name and len(name) > 1:
                        blends.append(name)
            continue

        if re.match(r"^Питательные добавки|^Средства по уходу|^Сыворотки|^Кремы", line):
            mode = None
            continue

        if mode is None:
            continue

        # Parse continuation lines: "4 OilName (Russian)," pattern
        # Lines may contain multiple items separated by commas
        # Also handle lines like "(Копайба) Смеси:" which mix mode
        if "Смеси:" in line and mode == "oils":
            parts = line.split("Смеси:", 1)
            # Left part: more oils
            for tok in re.split(r",", parts[0]):
                name = _extract_oil_name_from_token(tok)
                if name and len(name) > 1 and not name.startswith("("):
                    oils.append(name)
            # Right part: blend names
            mode = "blends"
            for tok in re.split(r",", parts[1]):
                name = _extract_oil_name_from_token(tok)
                if name and len(name) > 1:
                    blends.append(name)
            continue

        target = oils if mode == "oils" else blends
        for tok in re.split(r",", line):
            name = _extract_oil_name_from_token(tok)
            if name and len(name) > 1 and len(name) < 60:
                # Skip obvious garbage
                if re.match(r"^\d+$", name):
                    continue
                if re.match(r"^(см\.|стр\.|глав)", name, re.I):
                    continue
                target.append(name)

    # Clean up: remove entries that look like supplements (contain numbers, "ImmuPro" etc.)
    supplement_re = re.compile(r"^\d|^Super|^OmegaGize|^MegaCal|^Mineral|^Life 5|^NingXia|^ImmuPro|^Power|^Thyromin|^SleepEss|^PD 80|^Detox|^Digest|^Comfort|^Essen|^Alka|^Multi|^Sulfur|^JuvaPower|^ICP|^ComforT", re.I)

    def is_valid_oil_name(name: str) -> bool:
        if supplement_re.match(name):
            return False
        if len(name) < 2 or len(name) > 50:
            return False
        if re.match(r"^\d", name):
            return False
        return True

    oils = [o for o in oils if is_valid_oil_name(o)]
    blends = [b for b in blends if is_valid_oil_name(b)]

    # Deduplicate while preserving order
    seen: set[str] = set()
    oils_dedup = []
    for o in oils:
        if o.lower() not in seen:
            seen.add(o.lower())
            oils_dedup.append(o)
    seen.clear()
    blends_dedup = []
    for b in blends:
        if b.lower() not in seen:
            seen.add(b.lower())
            blends_dedup.append(b)

    return oils_dedup, blends_dedup


def _preprocess_symptom_lines(lines: list[str]) -> list[str]:
    """Merge lines where parenthetical oil names are split across lines."""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # If line ends with "(" (unclosed paren), merge with next
        open_parens = stripped.count("(") - stripped.count(")")
        if open_parens > 0 and i + 1 < len(lines):
            merged = stripped + " " + lines[i + 1].strip()
            result.append(merged)
            i += 2
            continue
        result.append(line)
        i += 1
    return result


def _is_valid_symptom_name(name: str) -> bool:
    """Validate that a string looks like a symptom/condition name."""
    # Must have at least 3 chars
    if len(name) < 3:
        return False
    # Max length
    if len(name) > 90:
        return False
    # Must start with uppercase Cyrillic
    if not re.match(r"^[А-ЯЁ]", name):
        return False
    # Should not end with a comma, period, or lone closing paren (split content)
    if name.endswith(",") or name.endswith(";") or name.endswith(")"):
        return False
    # Should not be just punctuation
    if re.match(r"^[\s\W]+$", name):
        return False
    # Skip lines that are clearly description text (contain articles + verbs)
    skip_words = ["является", "представляет", "характеризуется", "вызван", "возникает",
                  "приводит", "происходит", "развивается", "относится", "содержит",
                  "обеспечивает", "способствует", "можно", "помогает", "может быть",
                  "следует", "рекомендуется", "известно", "называется", "используется",
                  "добавьте", "нанесите", "принимайте", "применяйте", "смешайте",
                  "вдыхайте", "распыляйте", "массируйте",
                  ]
    name_lower = name.lower()
    if any(w in name_lower for w in skip_words):
        return False
    # Must contain at least one Cyrillic letter
    if not re.search(r"[а-яёА-ЯЁ]", name):
        return False
    # Skip lines with too many lowercase Cyrillic words (description, not name)
    words = name.split()
    if len(words) > 1:
        lowercase_count = sum(1 for w in words if w and w[0].islower())
        if lowercase_count > 2:
            return False
    return True


def parse_symptoms(lines: list[str], sym_start: int) -> list[dict]:
    """
    Parse symptom entries.
    Strategy:
      - Preprocess lines to merge split parentheticals
      - Scan for ALL-CAPS or Title-Case Cyrillic lines
      - For each candidate, look ahead up to 80 lines for 'Одинарные:' or 'Смеси:'
      - If found, treat the candidate as a symptom name and collect the recommendations
      - Otherwise treat as a category group header
    """
    entries: list[dict] = []
    current_category = "ОБЩЕЕ СОСТОЯНИЕ ОРГАНИЗМА"
    current_parent_group = ""  # top-level section (CAPS without indent)
    # Preprocess: merge multi-line parentheticals in symptom section
    lines = list(lines)  # copy
    lines[sym_start:] = _preprocess_symptom_lines(lines[sym_start:])
    i = sym_start

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1

        if not line:
            continue

        # Skip known noise
        if _is_skip_line(line):
            continue

        # Skip lines that clearly aren't symptom names
        if not SYMPTOM_NAME_RE.match(line):
            continue

        # Apply strict symptom name validation
        if not _is_valid_symptom_name(line):
            continue

        # ALL-CAPS lines (< 60 chars) are always section/category headers, not symptoms.
        # Classify by indentation and skip look-ahead.
        if line == line.upper() and len(line) < 60:
            has_indent = len(raw) > len(raw.lstrip())
            if has_indent:
                current_category = line
            else:
                current_parent_group = line
                current_category = line  # reset sub-group on new top section
            continue

        # Look ahead up to 80 lines for Одинарные: or Смеси:
        look_ahead_end = min(i + 80, len(lines))
        has_recs = False
        recs_start = -1
        for j in range(i, look_ahead_end):
            ahead = lines[j].strip()
            if re.match(r"^(Одинарные|Эфирные масла|Смеси)\s*:", ahead):
                has_recs = True
                recs_start = j
                break
            # If we hit another CAPS-line (likely a new symptom) before finding recs
            # treat the current line as category header
            if j > i + 5 and ahead and SYMPTOM_NAME_RE.match(ahead) and ahead != line:
                break

        if not has_recs:
            continue

        # Found a symptom! Collect its block
        # The block extends until the next symptom-candidate or a known stop marker
        symptom_name = line

        # Find the end of this symptom's recommendation block
        # Stop at: next symptom-like ALL-CAPS line, or СПОСОБЫ ПРИМЕНЕНИЯ
        block_end = recs_start
        while block_end < min(recs_start + 80, len(lines)):
            ahead = lines[block_end].strip()
            if ahead == "СПОСОБЫ ПРИМЕНЕНИЯ":
                break
            # Another symptom candidate
            if SYMPTOM_NAME_RE.match(ahead) and ahead != symptom_name and block_end > recs_start + 3:
                look = block_end + 1
                next_has_recs = False
                while look < min(block_end + 30, len(lines)):
                    if re.match(r"^(Одинарные|Эфирные масла|Смеси)\s*:", lines[look].strip()):
                        next_has_recs = True
                        break
                    look += 1
                if next_has_recs:
                    break
            block_end += 1

        oils, blends = _collect_oils_and_blends(lines, recs_start, block_end)

        if not oils and not blends:
            continue

        slug = "symptom-" + slugify(symptom_name)
        # Keep slug from getting too long
        if len(slug) > 80:
            # Use first 3 words
            words = re.split(r"[\s-]+", symptom_name.lower())[:3]
            slug = "symptom-" + "-".join(words)

        entry = {
            "slug": slug,
            "name": symptom_name,
            "category": "symptom",
            "source_type": "symptom",
            "aliases": [],
            "payload": {
                "parent_group": current_parent_group,
                "category_group": current_category,
                "recommended_oil_names": oils,
                "recommended_blend_names": blends,
                "applications": "",
                "description": "",
            },
        }
        entries.append(entry)
        i = block_end  # resume after this block

    return entries


def resolve_oil_slug(name: str) -> str | None:
    """Resolve an oil name (English or Russian) to a slug."""
    name_lower = name.lower().strip()
    # Direct slug match
    if name_lower in EXISTING_SLUG_BY_EN_NAME:
        return EXISTING_SLUG_BY_EN_NAME[name_lower]
    if name_lower in RU_TO_SLUG:
        return RU_TO_SLUG[name_lower]
    # Partial match
    for key, slug in EXISTING_SLUG_BY_EN_NAME.items():
        if key in name_lower or name_lower in key:
            return slug
    for key, slug in RU_TO_SLUG.items():
        if key in name_lower:
            return slug
    return None


def resolve_blend_slug(name: str, blend_slugs: dict[str, str]) -> str | None:
    """Resolve a blend name to its slug."""
    name_lower = name.lower().strip()
    for key, slug in blend_slugs.items():
        if key == name_lower or name_lower in key or key in name_lower:
            return slug
    return None


def main() -> None:
    if not PDF_TEXT.exists():
        print(f"ERROR: {PDF_TEXT} not found")
        sys.exit(1)

    text = PDF_TEXT.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    print(f"Loaded {len(lines)} lines from {PDF_TEXT}")

    # Find section boundaries
    blend_start = find_section_start(lines, BLEND_SECTION_HEADER)
    symptom_start_candidates = [i for i, l in enumerate(lines) if l.strip() == SYMPTOM_SECTION_HEADER]

    # Use the last occurrence (it appears in TOC and then in actual content)
    symptom_start = symptom_start_candidates[-1] if symptom_start_candidates else -1

    # Oils are between ~line 2340 (first OIL_NAME_RE match after intro) and blend_start
    # Find the first oil entry
    oil_section_start = 0
    for i, line in enumerate(lines):
        if OIL_NAME_RE.match(line.strip()) and i > 2300:
            oil_section_start = i
            break

    print(f"Oil section: lines {oil_section_start}–{blend_start}")
    print(f"Blend section: lines {blend_start}–{symptom_start}")
    print(f"Symptom section: lines {symptom_start}–end")

    # ── Parse oils ───────────────────────────────────────────────────────────
    oil_entries = parse_oils(lines, oil_section_start, blend_start if blend_start > 0 else symptom_start)
    print(f"Parsed {len(oil_entries)} oil entries")

    # Split into patch (existing) and new
    oils_patch = []
    oils_new = []
    existing_slugs = set(EXISTING_SLUG_BY_EN_NAME.values())

    for entry in oil_entries:
        en = entry["name_en"].lower()
        slug = EXISTING_SLUG_BY_EN_NAME.get(en)
        if not slug:
            # Try partial match
            for key, s in EXISTING_SLUG_BY_EN_NAME.items():
                if key in en or en in key:
                    slug = s
                    break

        if slug:
            patch = {"slug": slug, "patch": {k: v for k, v in entry.items() if v}}
            oils_patch.append(patch)
        else:
            # New oil card
            slug = slugify(entry["name_en"])
            ru_name = entry.get("name_ru") or entry["name_en"]
            card = {
                "slug": slug,
                "name": ru_name or entry["name_en"],
                "category": "aroma",
                "source_type": "herb",
                "aliases": [entry["name_en"]] if entry.get("name_en") else [],
                "payload": {
                    "name_en": entry["name_en"],
                    "name_ru": ru_name,
                    "key": ru_name or entry["name_en"],
                    "article_number": entry.get("article_number", ""),
                    "therapeutic_properties": entry.get("therapeutic_properties", ""),
                    "conditions_for_use": entry.get("conditions_for_use", ""),
                    "applications": entry.get("applications", ""),
                    "blends_containing_names": entry.get("blends_containing_names", []),
                    "complementary_oil_names": entry.get("complementary_oil_names", []),
                    "precautions": entry.get("precautions", ""),
                    "spiritual_emotional": entry.get("spiritual_emotional", ""),
                    "mind_effect": entry.get("mind_effect", ""),
                    "health_effects": entry.get("health_effects", ""),
                    "extraction_method": entry.get("extraction_method", ""),
                },
            }
            oils_new.append(card)

    print(f"  → {len(oils_patch)} patches for existing oils")
    print(f"  → {len(oils_new)} new oil cards")

    # ── Parse blends ─────────────────────────────────────────────────────────
    if blend_start > 0:
        blend_end = symptom_start if symptom_start > blend_start else len(lines)
        blend_entries = parse_blends(lines, blend_start, blend_end)
        print(f"Parsed {len(blend_entries)} blend entries")
    else:
        blend_entries = []
        print("WARNING: Blend section not found!")

    # ── Parse symptoms ───────────────────────────────────────────────────────
    if symptom_start > 0:
        symptom_entries = parse_symptoms(lines, symptom_start)
        # Deduplicate by slug
        seen_slugs: set[str] = set()
        unique_symptoms = []
        for s in symptom_entries:
            if s["slug"] not in seen_slugs:
                seen_slugs.add(s["slug"])
                unique_symptoms.append(s)
        symptom_entries = unique_symptoms
        print(f"Parsed {len(symptom_entries)} symptom entries")
    else:
        symptom_entries = []
        print("WARNING: Symptom section not found!")

    # ── Slug resolution pass ─────────────────────────────────────────────────
    # Build blend name → slug map
    blend_slug_map: dict[str, str] = {}
    for b in blend_entries:
        blend_slug_map[b["name"].lower()] = b["slug"]
        for alias in b.get("aliases", []):
            blend_slug_map[alias.lower()] = b["slug"]

    # Build all oil name → slug map (existing + new)
    all_oil_slug_map: dict[str, str] = dict(EXISTING_SLUG_BY_EN_NAME)
    for card in oils_new:
        all_oil_slug_map[card["name"].lower()] = card["slug"]
        for alias in card.get("aliases", []):
            all_oil_slug_map[alias.lower()] = card["slug"]
    for k, v in RU_TO_SLUG.items():
        all_oil_slug_map[k] = v

    # Resolve blend payloads
    for blend in blend_entries:
        p = blend["payload"]
        ing_names = p.get("ingredient_names", [])
        p["ingredient_slugs"] = []
        for name in ing_names:
            # Try to match English name from "Name (Russian)" pattern
            m = re.match(r"^(.+?)\s*\([^)]+\)$", name)
            en_part = m.group(1).strip() if m else name
            slug = all_oil_slug_map.get(en_part.lower()) or all_oil_slug_map.get(name.lower())
            p["ingredient_slugs"].append(slug or "")

        comp_names = p.get("complementary_oil_names", [])
        p["complementary_oil_slugs"] = []
        for name in comp_names:
            m = re.match(r"^(.+?)\s*\([^)]+\)$", name)
            en_part = m.group(1).strip() if m else name
            slug = all_oil_slug_map.get(en_part.lower()) or all_oil_slug_map.get(name.lower())
            p["complementary_oil_slugs"].append(slug or "")

    # Resolve oil patch complementary / blends_containing
    for patch in oils_patch:
        p = patch["patch"]
        comp_names = p.get("complementary_oil_names", [])
        p["complementary_oil_slugs"] = []
        for name in comp_names:
            slug = all_oil_slug_map.get(name.lower())
            p["complementary_oil_slugs"].append(slug or "")

        blend_names = p.get("blends_containing_names", [])
        p["blends_containing_slugs"] = []
        for name in blend_names:
            slug = blend_slug_map.get(name.lower())
            p["blends_containing_slugs"].append(slug or "")

    # Resolve new oil complementary / blends_containing
    for card in oils_new:
        p = card["payload"]
        comp_names = p.get("complementary_oil_names", [])
        p["complementary_oil_slugs"] = []
        for name in comp_names:
            slug = all_oil_slug_map.get(name.lower())
            p["complementary_oil_slugs"].append(slug or "")

        blend_names = p.get("blends_containing_names", [])
        p["blends_containing_slugs"] = []
        for name in blend_names:
            slug = blend_slug_map.get(name.lower())
            p["blends_containing_slugs"].append(slug or "")

    # Resolve symptoms
    for sym in symptom_entries:
        p = sym["payload"]
        oil_names = p.get("recommended_oil_names", [])
        p["recommended_oil_slugs"] = []
        for name in oil_names:
            m = re.match(r"^(.+?)\s*\([^)]+\)$", name)
            en_part = m.group(1).strip() if m else name
            slug = all_oil_slug_map.get(en_part.lower()) or all_oil_slug_map.get(name.lower())
            p["recommended_oil_slugs"].append(slug or "")

        blend_names = p.get("recommended_blend_names", [])
        p["recommended_blend_slugs"] = []
        for name in blend_names:
            slug = blend_slug_map.get(name.lower())
            p["recommended_blend_slugs"].append(slug or "")

    # ── Write output files ───────────────────────────────────────────────────
    OUT_DIR.mkdir(exist_ok=True)

    out_patch = OUT_DIR / "pdf_oils_patch.json"
    out_new = OUT_DIR / "pdf_oils_new.json"
    out_blends = OUT_DIR / "pdf_blends.json"
    out_symptoms = OUT_DIR / "pdf_symptoms.json"

    out_patch.write_text(json.dumps(oils_patch, ensure_ascii=False, indent=2), encoding="utf-8")
    out_new.write_text(json.dumps(oils_new, ensure_ascii=False, indent=2), encoding="utf-8")
    out_blends.write_text(json.dumps(blend_entries, ensure_ascii=False, indent=2), encoding="utf-8")
    out_symptoms.write_text(json.dumps(symptom_entries, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nOutput files:")
    print(f"  {out_patch} ({len(oils_patch)} entries)")
    print(f"  {out_new} ({len(oils_new)} entries)")
    print(f"  {out_blends} ({len(blend_entries)} entries)")
    print(f"  {out_symptoms} ({len(symptom_entries)} entries)")

    # Sample output
    if oils_patch:
        print(f"\nSample patch (first):")
        print(json.dumps(oils_patch[0], ensure_ascii=False, indent=2)[:600])
    if blend_entries:
        print(f"\nSample blend (first):")
        print(json.dumps(blend_entries[0], ensure_ascii=False, indent=2)[:600])
    if symptom_entries:
        print(f"\nSample symptom (first):")
        print(json.dumps(symptom_entries[0], ensure_ascii=False, indent=2)[:400])


if __name__ == "__main__":
    main()
