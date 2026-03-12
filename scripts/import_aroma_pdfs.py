from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = Path("/Users/p.kutsenko/Downloads")
OUTPUT = ROOT / "data" / "aroma_cards_seed.json"

DEFAULT_QUESTIONS = (
    "Какая тема этого масла сейчас наиболее откликается?\n"
    "Где в вашей жизни не хватает этого ресурса?\n"
    "Что меняется, если посмотреть на ситуацию через ресурс этого масла?"
)

PDF_SPECS = {
    "АПЕЛЬСИН.pdf": {"slug": "orange", "source_type": "citrus"},
    "БАЗИЛИК.pdf": {"slug": "basil", "source_type": "herb"},
    "БЕРГАМОТ.pdf": {"slug": "bergamot", "source_type": "citrus"},
    "БЕССМЕРТНИК.pdf": {"slug": "helichrysum", "source_type": "flower"},
    "ВЕТИВЕР.pdf": {"slug": "vetiver", "source_type": "grass"},
    "ГВОЗДИКА.pdf": {"slug": "clove", "source_type": "spice"},
    "ГЕРАНЬ.pdf": {"slug": "geranium", "source_type": "flower"},
    "ГРЕЙПФРУТ.pdf": {"slug": "grapefruit", "source_type": "citrus"},
    "ЖАСМИН.pdf": {"slug": "jasmine", "source_type": "flower"},
    "ИЛАНГ-ИЛАНГ.pdf": {"slug": "ylang-ylang", "source_type": "flower"},
    "ИМБИРЬ.pdf": {"slug": "ginger", "source_type": "spice"},
    "КЕДР.pdf": {"slug": "cedarwood", "source_type": "tree"},
    "КИПАРИС.pdf": {"slug": "cypress", "source_type": "tree"},
    "КОПАИБА.pdf": {"slug": "copaiba", "source_type": "resin"},
    "КОРИЦА.pdf": {"slug": "cinnamon", "source_type": "spice"},
    "ЛАВАНДА.pdf": {"slug": "lavender", "source_type": "flower"},
    "ЛАДАН.pdf": {"slug": "frankincense", "source_type": "resin"},
    "ЛАЙМ.pdf": {"slug": "lime", "source_type": "citrus"},
    "ЛЕМОНГРАСС.pdf": {"slug": "lemongrass", "source_type": "grass"},
    "ЛИМОН.pdf": {"slug": "lemon", "source_type": "citrus"},
    "МАЙОРАН.pdf": {"slug": "marjoram", "source_type": "herb"},
    "МАНДАРИН.pdf": {"slug": "mandarin", "source_type": "citrus"},
    "МОЖЖЕВЕЛЬНИК.pdf": {"slug": "juniper", "source_type": "tree"},
    "МЯТА ПЕРЕЧНАЯ.pdf": {"slug": "peppermint", "source_type": "herb"},
    "НЕРОЛИ.pdf": {"slug": "neroli", "source_type": "flower"},
    "ПАЧУЛИ.pdf": {"slug": "patchouli", "source_type": "herb"},
    "ПИХТА БАЛЬЗАМИЧЕСКАЯ.pdf": {"slug": "balsam-fir", "source_type": "tree", "aliases": ["Пихта"]},
    "РОЗА.pdf": {"slug": "rose", "source_type": "flower"},
    "РОЗМАРИН.pdf": {"slug": "rosemary", "source_type": "herb"},
    "РОМАШКА ГЕРМАНСКАЯ.pdf": {"slug": "german-chamomile", "source_type": "flower", "aliases": ["Ромашка немецкая"]},
    "САНДАЛ.pdf": {"slug": "sandalwood", "source_type": "tree"},
    "ТИМЬЯН.pdf": {"slug": "thyme", "source_type": "herb"},
    "ФЕНХЕЛЬ.pdf": {"slug": "fennel", "source_type": "herb"},
    "ЦИТРОНЕЛЛА.pdf": {"slug": "citronella", "source_type": "grass"},
    "ЧАЙНОЕ ДЕРЕВО.pdf": {"slug": "tea-tree", "source_type": "tree"},
    "ШАЛФЕЙ МУСКАТНЫЙ.pdf": {"slug": "clary-sage", "source_type": "herb"},
    "ЭВКАЛИПТ.pdf": {"slug": "eucalyptus-globulus", "source_type": "tree", "aliases": ["Эвкалипт"]},
}

EXTRA_CARDS = [
    {
        "slug": "oregano",
        "name": "Орегано",
        "aliases": [],
        "source_type": "herb",
        "botanical_family": "",
        "origin_countries": "",
        "extraction_method": "",
        "key": "Воля завершать разрушающие отношения и выходить из зависимости.",
        "description": "Воля завершать разрушающие отношения или гнетущую работу, отпускание чрезмерной привязанности и зависимости, безопасность.",
        "questions": DEFAULT_QUESTIONS,
        "nps_effect": "Связан с темой воли, завершения нездоровых связей и ощущения безопасности.",
        "therapeutic_properties": "Нет данных из PDF. Поле можно дополнить вручную.",
        "psychological_properties": "Человек не может отпустить чрезмерную привязанность, зависимость и не чувствует себя в безопасности.",
        "resource_values": {"plus": "Способность завершать разрушительные связи и возвращать себе безопасность.", "minus": "Зависимость, уязвимость, нехватка воли на завершение."},
        "history": "Нет данных из PDF. Поле можно дополнить вручную.",
        "volatility": "",
    },
    {
        "slug": "cassia",
        "name": "Кассия",
        "aliases": [],
        "source_type": "spice",
        "botanical_family": "",
        "origin_countries": "",
        "extraction_method": "",
        "key": "Видеть свои тени и истинную ценность.",
        "description": "Помогает посмотреть на себя со стороны, снижает робость и стеснение, помогает расстаться с зависимостями, придает смелость пробовать новое.",
        "questions": DEFAULT_QUESTIONS,
        "nps_effect": "Связана с выходом из застенчивости, раскрытием талантов и внутренней ценности.",
        "therapeutic_properties": "Нет данных из PDF. Поле можно дополнить вручную.",
        "psychological_properties": "Даёт ощущение наполненности, раскрывает внутренние способности и таланты.",
        "resource_values": {"plus": "Смелость пробовать новое, контакт с талантами и ценностью.", "minus": "Робость, стеснение, зависимость, скрытые тени."},
        "history": "Нет данных из PDF. Поле можно дополнить вручную.",
        "volatility": "",
    },
    {
        "slug": "blue-spruce",
        "name": "Голубая ель",
        "aliases": [],
        "source_type": "tree",
        "botanical_family": "",
        "origin_countries": "",
        "extraction_method": "",
        "key": "Глубокий мир, безопасность, раскрытие уникальности.",
        "description": "Заземляет, помогает отпустить эмоциональные блоки, открыть сердце и довериться Вселенной.",
        "questions": DEFAULT_QUESTIONS,
        "nps_effect": "Поддерживает чувство мира, безопасности и контакт с собственной миссией.",
        "therapeutic_properties": "Влияние на ум: древесный аромат бодрит, дает душевное спокойствие и расслабляет тело, приносит ясность сознанию и уверенность в принятии решений.",
        "psychological_properties": "Помогает вспомнить забытые и подавленные эмоциональные блоки, чтобы с ними можно было работать и отпускать их.",
        "resource_values": {"plus": "Мир, безопасность, открытое сердце, принятие своей уникальности.", "minus": "Эмоциональные блоки, страх быть собой, недоверие миру."},
        "history": "В ваших материалах отмечено наблюдение доктора Коринны Ален о работе масла с забытыми и подавленными эмоциональными блоками.",
        "volatility": "",
    },
    {
        "slug": "black-pepper",
        "name": "Черный перец",
        "aliases": [],
        "source_type": "spice",
        "botanical_family": "",
        "origin_countries": "",
        "extraction_method": "",
        "key": "Внутренняя сила и защищенность.",
        "description": "Яркий аромат помогает оставить позади эмоциональные потрясения и обиды, мотивирует дышать свободной и радостной жизнью.",
        "questions": DEFAULT_QUESTIONS,
        "nps_effect": "Поддерживает внутреннюю силу, защищенность и спокойное выражение своих мыслей.",
        "therapeutic_properties": "Нет данных из PDF. Поле можно дополнить вручную.",
        "psychological_properties": "Помогает не сравнивать себя с другими, учит доброму отношению к себе и окружающим без критики и оценочных суждений.",
        "resource_values": {"plus": "Уверенность, защищенность, легкость во взаимоотношениях.", "minus": "Страх, нервозность, обиды, самоуничижение или превосходство."},
        "history": "Нет данных из PDF. Поле можно дополнить вручную.",
        "volatility": "",
    },
    {
        "slug": "spruce",
        "name": "Ель",
        "aliases": [],
        "source_type": "tree",
        "botanical_family": "",
        "origin_countries": "",
        "extraction_method": "",
        "key": "Избавление от лишнего.",
        "description": "Помогает избавиться от того, что больше не нужно.",
        "questions": DEFAULT_QUESTIONS,
        "nps_effect": "Поддерживает завершение и очищение от лишнего.",
        "therapeutic_properties": "Нет данных из PDF. Поле можно дополнить вручную.",
        "psychological_properties": "Связана с отпусканием ненужного.",
        "resource_values": {"plus": "Лёгкость завершения и очищение пространства жизни.", "minus": "Застревание в том, что давно пора отпустить."},
        "history": "Нет данных из PDF. Поле можно дополнить вручную.",
        "volatility": "",
    },
    {
        "slug": "kunzea",
        "name": "Кунцея",
        "aliases": [],
        "source_type": "herb",
        "botanical_family": "",
        "origin_countries": "",
        "extraction_method": "",
        "key": "Перемены, трансформация, потенциал будущего.",
        "description": "Про перемены, трансформацию, личностный рост, возможности и свободу.",
        "questions": DEFAULT_QUESTIONS,
        "nps_effect": "Поддерживает трансформацию и открытость потенциалу будущего.",
        "therapeutic_properties": "Нет данных из PDF. Поле можно дополнить вручную.",
        "psychological_properties": "Связана с возможностями, потенциалом будущего и внутренней свободой.",
        "resource_values": {"plus": "Готовность к росту и переменам.", "minus": "Сопротивление переменам, страх будущего."},
        "history": "Нет данных из PDF. Поле можно дополнить вручную.",
        "volatility": "",
    },
]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def section(text: str, start: str, *ends: str) -> str:
    pattern = re.escape(start) + r"\s*(.+?)\s*(?=" + "|".join(re.escape(item) for item in ends) + r"|$)"
    match = re.search(pattern, text, flags=re.S)
    return normalize_text(match.group(1)) if match else ""


def extract_pdf_card(path: Path, spec: dict[str, object]) -> dict[str, object]:
    raw_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    text = normalize_text(raw_text)
    title_match = re.match(r"^(.*?)\s*\(", text)
    name = title_match.group(1).strip() if title_match else path.stem
    botanical_family = section(text, "Ботаническое семейство:", "Страна происхождения:")
    origin_countries = section(text, "Страна происхождения:", "Способ получения:")
    extraction_method = section(text, "Способ получения:", "Ключ:")
    key = section(text, "Ключ:", "В эфире красоТЫ и здоровьЯ")
    history = section(text, "Исторические сведения", "Летучесть")
    volatility = section(text, "Летучесть", "Действие на НПС")
    nps_effect = section(text, "Действие на НПС", "Терапевтические свойства", "Терапевтические свойства")
    therapeutic = section(text, "Терапевтические свойства", "Психологические свойства", "Ресурсные значения «+» и «-»")
    psychological = section(text, "Психологические свойства", "Ресурсные значения «+» и «-»")
    resource = section(text, "Ресурсные значения «+» и «-»", "В эфире красоТЫ и здоровьЯ 1")
    plus_match = re.search(r"«\+»\s*[–-]?\s*(.+?)\s*«-»", resource)
    minus_match = re.search(r"«-»\s*[–-]?\s*(.+)$", resource)
    return {
        "slug": str(spec["slug"]),
        "name": name,
        "aliases": list(spec.get("aliases", [])),
        "source_type": str(spec.get("source_type", "herb")),
        "botanical_family": botanical_family,
        "origin_countries": origin_countries,
        "extraction_method": extraction_method,
        "key": key,
        "description": key or name,
        "questions": DEFAULT_QUESTIONS,
        "nps_effect": nps_effect,
        "therapeutic_properties": therapeutic or "Нет данных из PDF. Поле можно дополнить вручную.",
        "psychological_properties": psychological,
        "resource_values": {
            "plus": normalize_text(plus_match.group(1)) if plus_match else resource,
            "minus": normalize_text(minus_match.group(1)) if minus_match else "",
        },
        "history": history,
        "volatility": volatility,
    }


def main() -> None:
    items = []
    for filename, spec in PDF_SPECS.items():
        items.append(extract_pdf_card(DOWNLOADS / filename, spec))
    items.extend(EXTRA_CARDS)
    items.sort(key=lambda item: item["name"].lower().replace("ё", "е"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # This JSON is a generated seed/import artifact, not a runtime store.
    OUTPUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(items)} cards to {OUTPUT}")


if __name__ == "__main__":
    main()
