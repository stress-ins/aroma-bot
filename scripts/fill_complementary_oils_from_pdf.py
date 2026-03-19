"""Fill complementary_oil_names/slugs from hardcoded PDF data (base.pdf handbook).

Each oil in the Young Living handbook lists complementary oils.
This script writes those lists into AromaCardModel.payload so that the
miniapp can render the "Комплементарные масла" chip section.

Usage:
    .venv/bin/python scripts/fill_complementary_oils_from_pdf.py [--dry-run] [--force] [--slug SLUG]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Hardcoded data extracted from data/oil_pdfs/handbook_parts/base.pdf
# Key = English oil name (matches slug pattern or model.name)
# Value = list of Russian complementary oil names from the handbook
# ---------------------------------------------------------------------------
COMPLEMENTARY_MAP: dict[str, list[str]] = {
    "Angelica": [
        "Пачули", "Шалфей мускатный", "Базилик", "Лаванда", "Герань",
        "Ромашка", "Лимон", "Мандарин",
    ],
    "Balsam Fir Idaho": [
        "Корица", "Гвоздика", "Мускатный орех", "Черный перец", "Бергамот",
        "Розмарин", "Кипарис", "Можжевельник", "Вербена", "Цитронелла",
        "Лимон", "Сосна", "Майоран",
    ],
    "Basil": [
        "Бергамот", "Вербена", "Герань", "Имбирь", "Иссоп", "Лайм",
        "Мандарин", "Мята перечная", "Розовое дерево", "Цитронелла",
        "Шалфей мускатный",
    ],
    "Bergamot": [
        "Черный перец", "Мирт", "Имбирь", "Сосна", "Ель", "Мускатный орех",
        "Корица", "Шалфей", "Пихта", "Роза", "Ромашка", "Сандал", "Чабрец",
        "Базилик", "Ветивер", "Гвоздика", "Душица", "Иланг-иланг",
        "Можжевельник", "Кипарис", "Ладан", "Лимон", "Майоран", "Мандарин",
        "Мелисса", "Мята перечная", "Найоли", "Пальмароза", "Пачули",
        "Чайное дерево", "Лаванда", "Жасмин", "Герань", "Кориандр",
    ],
    "Carrot Seed": [
        "Лаванда", "Роза", "Кассия", "Кедр", "Сандал", "Ветивер",
    ],
    "Cassia": ["Апельсин"],
    "Cedarwood": [
        "Грейпфрут", "Бергамот", "Жасмин", "Можжевельник", "Сандал", "Роза",
        "Кипарис", "Пачули", "Шалфей", "Розмарин", "Иланг-иланг",
        "Розовое дерево", "Вербена", "Нероли", "Цитронелла", "Пальмароза",
        "Чабрец",
    ],
    "Cinnamon Bark": [
        "Цитронелла", "Грейпфрут", "Апельсин", "Можжевельник", "Шалфей",
        "Роза", "Иланг-иланг", "Бергамот", "Черный перец", "Лаванда",
        "Мандарин", "Мирра", "Мирт", "Пихта", "Розмарин", "Чайное дерево",
    ],
    "Cistus": [
        "Сосна", "Можжевельник", "Лаванда", "Бергамот", "Кипарис", "Ветивер",
        "Сандал", "Пачули", "Шалфей мускатный", "Бессмертник", "Апельсин",
    ],
    "Citronella": [
        "Пачули", "Корица", "Гвоздика", "Иланг-иланг", "Ветивер", "Сандал",
        "Ладан", "Черный перец", "Кипарис", "Базилик", "Можжевельник",
        "Лаванда", "Мята перечная", "Найоли", "Пихта", "Розмарин", "Чабрец",
        "Шалфей", "Герань", "Лимон", "Бергамот", "Апельсин", "Кедр", "Сосна",
    ],
    "Clary Sage": [
        "Роза", "Герань", "Розовое дерево", "Бергамот", "Сосна", "Гвоздика",
        "Корица", "Мускатный орех", "Цитронелла", "Лаванда", "Анис",
        "Апельсин", "Иссоп", "Кедр", "Мирт", "Пачули", "Ладан",
        "Черный перец", "Розмарин", "Лемонграсс",
    ],
    "Clove": [
        "Грейпфрут", "Можжевельник", "Роза", "Иланг-иланг", "Шалфей",
        "Бергамот", "Черный перец", "Имбирь", "Лаванда", "Лимон", "Мандарин",
        "Мирра", "Мирт", "Пихта", "Розмарин", "Чайное дерево",
        "Шалфей мускатный", "Апельсин",
    ],
    "Copaiba": [
        "Сандал", "Иланг-иланг", "Жасмин", "Роза", "Ладан", "Мята перечная",
        "Кедр", "Корица", "Гвоздика",
    ],
    "Davana": ["Ладан", "Роза"],
    "Dill": ["Элеми", "Мята перечная", "Тмин", "Мускатный орех"],
    "Elemi": ["Лимон", "Розмарин", "Укроп", "Лаванда", "Шалфей", "Корица"],
    "Eucalyptus Blue": [
        "Нероли", "Розмарин", "Лаванда", "Кедр", "Лимон", "Петитгрейн",
        "Апельсин", "Розовое дерево", "Ветивер", "Герань",
    ],
    "Eucalyptus Globulus": [
        "Нероли", "Розмарин", "Лаванда", "Кедр", "Лимон", "Петитгрейн",
        "Апельсин", "Розовое дерево", "Ветивер", "Герань",
    ],
    "Eucalyptus Radiata": [
        "Нероли", "Розмарин", "Лаванда", "Кедр", "Лимон", "Петитгрейн",
        "Апельсин", "Розовое дерево", "Ветивер", "Герань",
    ],
    "Fennel": [
        "Мелисса", "Лаванда", "Герань", "Мята перечная", "Мускатный орех",
        "Розовое дерево", "Сандал", "Ель", "Лемонграсс",
    ],
    "Frankincense": [
        "Сандал", "Роза", "Черный перец", "Лаванда", "Сосна", "Кипарис",
        "Шалфей", "Апельсин", "Бергамот", "Розмарин", "Грейпфрут", "Мирра",
        "Можжевельник", "Нероли", "Цитронелла", "Эвкалипт", "Базилик",
        "Пачули",
    ],
    "Geranium": [
        "Эвкалипт", "Кипарис", "Сосна", "Цитронелла", "Чайное дерево",
        "Шалфей", "Базилик", "Иссоп", "Сандал", "Лимон", "Мелисса", "Мирт",
        "Мята перечная", "Ромашка", "Лаванда", "Пачули", "Гвоздика", "Роза",
        "Жасмин", "Можжевельник", "Бергамот",
    ],
    "German Chamomile": [
        "Герань", "Лаванда", "Роза", "Бергамот", "Жасмин",
        "Шалфей мускатный",
    ],
    "Ginger": [
        "Можжевельник", "Жасмин", "Ладан", "Нероли", "Лиметт", "Лаванда",
        "Мята перечная", "Гвоздика", "Роза", "Вербена", "Бергамот",
        "Базилик", "Мелисса", "Пачули", "Чабрец", "Лемонграсс",
    ],
    "Grapefruit": [
        "Черный перец", "Ветивер", "Пачули", "Мирт", "Ладан", "Мирра",
        "Гвоздика", "Мускатный орех", "Душица", "Кедр", "Корица", "Майоран",
        "Пальмароза", "Имбирь", "Нероли", "Кипарис", "Лимон", "Бергамот",
        "Лаванда", "Герань", "Кардамон",
    ],
    "Helichrysum": [
        "Апельсин", "Бергамот", "Ветивер", "Гвоздика", "Герань", "Кипарис",
        "Лаванда", "Ладан", "Мандарин", "Роза", "Ромашка", "Сандал",
        "Шалфей мускатный",
    ],
    "Juniper": [
        "Герань", "Апельсин", "Бергамот", "Сосна", "Кипарис", "Мирра",
        "Сандал", "Ладан", "Ветивер", "Пачули", "Чабрец", "Гвоздика",
        "Имбирь", "Корица", "Майоран", "Лаванда", "Мускатный орех",
        "Черный перец", "Пихта", "Цитронелла",
    ],
    "Lavender": [
        "Мирт", "Гвоздика", "Корица", "Цитронелла", "Кипарис", "Герань",
        "Пачули", "Шалфей", "Розмарин", "Ромашка", "Фенхель",
        "Чайное дерево", "Сосна", "Валериана", "Ладан", "Сандал", "Имбирь",
        "Лимон", "Майоран", "Мирра", "Мускатный орех", "Роза",
        "Можжевельник", "Чабрец", "Иссоп",
    ],
    "Laurus Nobilis": [
        "Сосна", "Кипарис", "Можжевельник", "Шалфей мускатный", "Розмарин",
        "Лаванда", "Ладан",
    ],
    "Lemon": [
        "Иланг-иланг", "Герань", "Лаванда", "Пальмароза", "Имбирь",
        "Кардамон", "Бергамот", "Можжевельник", "Нероли", "Гвоздика",
        "Кипарис", "Жасмин", "Роза", "Ромашка", "Сандал", "Фенхель",
        "Эвкалипт", "Ладан", "Чабрец",
    ],
    "Lemongrass": [
        "Нероли", "Бергамот", "Имбирь", "Жасмин", "Иланг-иланг",
        "Розовое дерево", "Мирт", "Шалфей", "Апельсин", "Анис", "Фенхель",
        "Ладан", "Сандал", "Черный перец", "Чабрец",
    ],
    "Lime": [
        "Иланг-иланг", "Пальмароза", "Лаванда", "Герань", "Бергамот",
        "Нероли", "Гвоздика", "Кипарис", "Жасмин", "Чабрец",
    ],
    "Manuka": ["Лаванда", "Мелисса", "Шалфей", "Чайное дерево"],
    "Marjoram": [
        "Роза", "Пачули", "Грейпфрут", "Сандал", "Кипарис", "Лаванда",
        "Розовое дерево", "Можжевельник", "Бергамот", "Жасмин", "Мандарин",
    ],
    "Melissa": [
        "Имбирь", "Лаванда", "Герань", "Роза", "Розовое дерево",
        "Иланг-иланг", "Нероли",
    ],
    "Myrrh": [
        "Герань", "Грейпфрут", "Лаванда", "Сандал", "Можжевельник",
        "Кипарис", "Ветивер", "Пачули", "Сосна", "Розовое дерево", "Роза",
        "Ладан", "Корица", "Гвоздика", "Мускатный орех", "Нероли",
    ],
    "Myrtle": [
        "Пачули", "Розмарин", "Шалфей", "Корица", "Кипарис", "Роза",
        "Герань", "Бергамот", "Валериана", "Ветивер", "Грейпфрут", "Иссоп",
        "Лаванда", "Сосна", "Лемонграсс", "Цитронелла",
        "Шалфей мускатный", "Гвоздика",
    ],
    "Northern Lights Black Spruce": [
        "Кедр", "Роза", "Розмарин", "Эвкалипт", "Найоли", "Лаванда",
        "Лимон", "Шалфей", "Сосна", "Апельсин", "Бергамот", "Грейпфрут",
    ],
    "Orange": [
        "Лаванда", "Герань", "Роза", "Иланг-иланг", "Можжевельник",
        "Жасмин", "Чабрец", "Корица", "Ладан", "Мускатный орех", "Шалфей",
        "Ромашка", "Гвоздика", "Кориандр", "Кипарис", "Орегано",
        "Черный перец", "Душица", "Ель", "Лемонграсс", "Эвкалипт", "Лимон",
    ],
    "Oregano": [
        "Мята перечная", "Грейпфрут", "Апельсин", "Анис", "Лаванда",
        "Эвкалипт", "Сосна", "Розмарин", "Кедр", "Бергамот", "Лимон",
    ],
    "Palmarosa": [
        "Герань", "Грейпфрут", "Иланг-иланг", "Кедр", "Роза",
        "Розовое дерево", "Вербена", "Лимон", "Петитгрейн", "Сандал",
    ],
    "Patchouli": [
        "Имбирь", "Ветивер", "Гвоздика", "Грейпфрут", "Лаванда", "Жасмин",
        "Бергамот", "Вербена", "Шалфей", "Сосна", "Кипарис", "Мирра",
        "Мускатный орех", "Нероли",
    ],
    "Peppermint": [
        "Бергамот", "Имбирь", "Иланг-иланг", "Базилик", "Лаванда", "Герань",
        "Жасмин", "Апельсин", "Мандарин", "Найоли", "Мускатный орех",
        "Эвкалипт", "Розмарин", "Цитронелла", "Лиметт", "Розовое дерево",
        "Душица", "Фенхель", "Чабрец",
    ],
    "Pine": [
        "Мирт", "Можжевельник", "Лаванда", "Розмарин", "Иланг-иланг",
        "Ладан", "Вербена", "Розовое дерево", "Бергамот", "Валериана",
        "Ветивер", "Герань", "Мирра", "Нероли", "Пачули", "Цитронелла",
        "Чайное дерево", "Шалфей",
    ],
    "Roman Chamomile": [
        "Герань", "Лаванда", "Роза", "Бергамот", "Жасмин",
        "Шалфей мускатный",
    ],
    "Rose": ["Пальмароза", "Жасмин", "Сандал", "Бергамот"],
    "Rosemary": [
        "Вербена", "Гвоздика", "Кедр", "Корица", "Кипарис", "Лаванда",
        "Ладан", "Лиметт", "Мирт", "Мускатный орех", "Мята перечная",
        "Петитгрейн", "Пихта", "Ромашка", "Сосна", "Цитронелла", "Чабрец",
        "Черный перец", "Шалфей", "Эвкалипт",
    ],
    "Sacred Frankincense": [
        "Розовое дерево", "Сандал", "Нероли", "Роза", "Вербена",
        "Черный перец", "Лаванда", "Сосна", "Кипарис", "Шалфей", "Апельсин",
        "Бергамот", "Розмарин", "Грейпфрут", "Мирра", "Можжевельник",
        "Нероли", "Цитронелла", "Эвкалипт",
    ],
    "Sage": [
        "Анис", "Апельсин", "Бергамот", "Гвоздика", "Герань", "Имбирь",
        "Иссоп", "Кедр", "Корица", "Лаванда", "Лавр благородный",
        "Лемонграсс", "Мелисса", "Мирт", "Мускатный орех", "Найоли",
        "Нероли", "Пачули", "Петитгрейн", "Роза", "Розовое дерево", "Сосна",
        "Цитронелла", "Черный перец",
    ],
    "Sandalwood": [
        "Роза", "Лаванда", "Бергамот", "Герань", "Черный перец", "Пачули",
        "Жасмин", "Кедр", "Кипарис", "Майоран", "Можжевельник",
        "Мускатный орех", "Фенхель", "Цитронелла", "Мирра", "Лемонграсс",
    ],
    "Spearmint": [
        "Эвкалипт", "Иланг-иланг", "Лаванда", "Розмарин", "Жасмин",
        "Герань", "Цитронелла", "Базилик", "Бергамот", "Лиметт",
        "Розовое дерево", "Мандарин", "Имбирь", "Апельсин", "Душица",
        "Мускатный орех", "Найоли", "Нероли", "Петитгрейн", "Фенхель",
        "Чабрец",
    ],
    "Tea Tree": ["Розмарин", "Мелисса"],
    "Thyme": [
        "Имбирь", "Кипарис", "Бергамот", "Розмарин", "Мелисса",
        "Мята перечная", "Лаванда", "Можжевельник", "Цитронелла",
        "Лемонграсс",
    ],
    "Valerian": [
        "Розовое дерево", "Пачули", "Ель", "Мирт", "Сосна", "Лаванда",
        "Кипарис", "Мандарин",
    ],
    # --- Oils not in base.pdf — data from aromatherapy references ---
    "Benzoin": [
        "Ладан", "Мирра", "Сандал", "Роза", "Жасмин", "Апельсин",
        "Лимон", "Бергамот", "Кипарис", "Можжевельник", "Корица",
    ],
    "Blue Spruce": [
        "Кедр", "Сосна", "Ладан", "Лаванда", "Розмарин", "Апельсин",
        "Бергамот", "Грейпфрут", "Кипарис", "Можжевельник",
    ],
    "Fragonia": [
        "Чайное дерево", "Эвкалипт", "Лаванда", "Лимон", "Бергамот",
        "Герань", "Розмарин", "Мята перечная",
    ],
    "Ho Wood": [
        "Роза", "Лаванда", "Герань", "Иланг-иланг", "Бергамот",
        "Ладан", "Сандал", "Нероли", "Жасмин", "Пачули",
    ],
    "Kunzea": [
        "Чайное дерево", "Эвкалипт", "Лаванда", "Розмарин",
        "Лемонграсс", "Мята перечная", "Сосна", "Кипарис",
    ],
    "Pink Pepper": [
        "Бергамот", "Грейпфрут", "Лимон", "Герань", "Роза",
        "Ладан", "Сандал", "Пачули", "Ветивер", "Имбирь",
    ],
    "Spruce": [
        "Кедр", "Сосна", "Ладан", "Лаванда", "Розмарин", "Бергамот",
        "Кипарис", "Можжевельник", "Эвкалипт", "Мирра",
    ],
    "Black Pepper": [
        "Можжевельник", "Бергамот", "Лаванда", "Мирра", "Ладан",
        "Сандал", "Герань", "Гвоздика", "Имбирь", "Лимон",
        "Пачули", "Розмарин", "Шалфей", "Фенхель",
    ],
    "Cypress": [
        "Бергамот", "Лаванда", "Можжевельник", "Лимон", "Апельсин",
        "Сосна", "Розмарин", "Сандал", "Шалфей мускатный",
    ],
    "Jasmine": [
        "Вербена", "Лимон", "Лиметт", "Черный перец", "Кедр",
        "Левзея", "Майоран", "Мята перечная", "Нероли",
        "Петитгрейн", "Роза", "Сандал", "Лемонграсс",
    ],
    "Neroli": [
        "Роза", "Лаванда", "Жасмин", "Бергамот", "Сандал",
        "Герань", "Ладан", "Апельсин", "Лимон", "Пачули",
        "Петитгрейн", "Иланг-иланг",
    ],
    "Tangerine": [
        "Пачули", "Бергамот", "Ветивер", "Иланг-иланг", "Гвоздика",
        "Корица", "Майоран", "Базилик", "Ель", "Мелисса",
        "Мята перечная",
    ],
    "Vetiver": [
        "Апельсин", "Мандарин", "Грейпфрут", "Лимон", "Лайм",
        "Жасмин", "Роза", "Сандал", "Герань", "Лаванда", "Корица",
        "Пачули", "Розовое дерево", "Шалфей мускатный",
    ],
    "Wintergreen": [
        "Иланг-иланг", "Мята перечная", "Тимьян", "Душица",
    ],
    "Ylang Ylang": [
        "Бергамот", "Жасмин", "Лаванда", "Роза", "Сандал",
        "Ветивер", "Грейпфрут", "Мандарин", "Герань", "Нероли",
        "Лимон", "Пачули", "Ладан",
    ],
}


# ---------------------------------------------------------------------------
# Override mappings for names that don't resolve automatically
# ---------------------------------------------------------------------------
EN_NAME_OVERRIDES: dict[str, str] = {
    "Balsam Fir Idaho": "balsam-fir",
    "Cinnamon Bark": "cinnamon",
    "Eucalyptus Blue": "eucaliptus-blue",
    "Northern Lights Black Spruce": "black-spruce",
    "Sacred Frankincense": "frankincense",
    "Tangerine": "mandarin",
}

EN_SKIP = {"Dill", "Eucalyptus Radiata", "Sage"}

RU_NAME_OVERRIDES: dict[str, str | None] = {
    "валериана": "valerian",
    "душица": "oregano",
    "лиметт": "lime",
    "мускатный орех": "nutmeg",
    "найоли": None,
    "розовое дерево": None,
    "чабрец": "thyme",
    "шалфей мускатный": "clary-sage",
    "шалфей": "clary-sage",
    "анис": None,
    "вербена": None,
    "кардамон": None,
    "кориандр": None,
    "укроп": None,
    "тимьян": "thyme",
    "левзея": None,
    "элеми": None,
    "тмин": None,
    "орегано": "oregano",
    "лавр благородный": "laurus-nobilis",
    "эвкалипт": "eucalyptus-globulus",
    "кассия": "cassia",
    "бессмертник": "helichrysum",
    "иссоп": None,
    "пихта": None,
    "ель": None,
}


def _normalize(name: str) -> str:
    """Lowercase + strip for fuzzy matching."""
    return name.strip().lower().replace("ё", "е")


async def run(dry_run: bool = False, force: bool = False, slug_filter: str | None = None) -> None:
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from sqlalchemy import select
    from datetime import datetime, timezone

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        all_models = result.scalars().all()

    print(f"Loaded {len(all_models)} aroma cards from DB.")

    # Build lookups: name_ru (normalized) → model, slug → model, EN name → model
    slug_to_model: dict[str, AromaCardModel] = {}
    name_ru_to_slug: dict[str, str] = {}
    name_en_to_slug: dict[str, str] = {}

    for m in all_models:
        slug_to_model[m.slug] = m
        payload = m.payload or {}
        # Russian name
        name_ru = payload.get("name") or m.name or ""
        if name_ru:
            name_ru_to_slug[_normalize(name_ru)] = m.slug
        # English name (often stored in model.name or payload.name_en)
        name_en = payload.get("name_en") or ""
        if name_en:
            name_en_to_slug[_normalize(name_en)] = m.slug
        # Slug itself often matches lowercase English name
        name_en_to_slug[_normalize(m.slug.replace("-", " "))] = m.slug
        # Aliases
        for alias in (m.aliases or []):
            name_ru_to_slug[_normalize(alias)] = m.slug
            name_en_to_slug[_normalize(alias)] = m.slug

    def find_card_slug(en_name: str) -> str | None:
        """Find aroma card slug by English name from COMPLEMENTARY_MAP key."""
        if en_name in EN_SKIP:
            return None
        if en_name in EN_NAME_OVERRIDES:
            override_slug = EN_NAME_OVERRIDES[en_name]
            if override_slug in slug_to_model:
                return override_slug
        norm = _normalize(en_name)
        # Direct match by EN name
        if norm in name_en_to_slug:
            return name_en_to_slug[norm]
        # Try slug-ified version
        slug_try = norm.replace(" ", "-")
        if slug_try in slug_to_model:
            return slug_try
        # Partial match
        for s, model in slug_to_model.items():
            if _normalize(s.replace("-", " ")) == norm:
                return s
        return None

    def resolve_complementary_slug(ru_name: str) -> str | None:
        """Resolve a Russian oil name to a slug."""
        norm = _normalize(ru_name)
        if norm in RU_NAME_OVERRIDES:
            override_slug = RU_NAME_OVERRIDES[norm]
            if override_slug is None:
                return None
            if override_slug in slug_to_model:
                return override_slug
        if norm in name_ru_to_slug:
            return name_ru_to_slug[norm]
        # Try partial/fuzzy: check if any known name starts with or contains
        for known_norm, known_slug in name_ru_to_slug.items():
            if norm in known_norm or known_norm in norm:
                return known_slug
        return None

    updated = 0
    skipped = 0
    not_found_cards: list[str] = []
    unresolved_names: set[str] = set()

    for en_name, comp_names_ru in COMPLEMENTARY_MAP.items():
        card_slug = find_card_slug(en_name)
        if not card_slug:
            not_found_cards.append(en_name)
            continue

        if slug_filter and card_slug != slug_filter:
            continue

        model = slug_to_model[card_slug]
        payload = model.payload or {}
        existing = payload.get("complementary_oil_names") or []

        if existing and not force:
            skipped += 1
            continue

        # Resolve each complementary oil name to slug
        valid_names: list[str] = []
        valid_slugs: list[str] = []
        for ru_name in comp_names_ru:
            resolved_slug = resolve_complementary_slug(ru_name)
            if resolved_slug and resolved_slug != card_slug:  # don't link to self
                valid_names.append(ru_name)
                valid_slugs.append(resolved_slug)
            elif resolved_slug is None and _normalize(ru_name) not in RU_NAME_OVERRIDES:
                unresolved_names.add(ru_name)

        if not valid_names:
            continue

        if dry_run:
            ru_display = (payload.get("name") or model.name or card_slug)
            print(f"  [DRY-RUN] {en_name} ({ru_display}): {len(valid_names)} oils → {valid_names[:5]}...")
            updated += 1
            continue

        new_payload = dict(payload)
        new_payload["complementary_oil_names"] = valid_names
        new_payload["complementary_oil_slugs"] = valid_slugs
        model.payload = new_payload
        model.updated_at = datetime.now(timezone.utc)
        updated += 1

    if not dry_run and updated > 0:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.category == "aroma")
            )
            db_models = {m.slug: m for m in result.scalars().all()}
            for en_name, comp_names_ru in COMPLEMENTARY_MAP.items():
                card_slug = find_card_slug(en_name)
                if not card_slug or (slug_filter and card_slug != slug_filter):
                    continue
                m = db_models.get(card_slug)
                if not m:
                    continue
                src = slug_to_model[card_slug]
                if src.payload != m.payload:
                    m.payload = src.payload
                    m.updated_at = src.updated_at
            await session.commit()

    print(f"\nResults: {updated} updated, {skipped} skipped (already filled)")
    if not_found_cards:
        print(f"Cards not found in DB: {not_found_cards}")
    if unresolved_names:
        print(f"Unresolved complementary oil names ({len(unresolved_names)}): {sorted(unresolved_names)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill complementary oils from PDF handbook data"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--force", action="store_true", help="Overwrite existing complementary oils")
    parser.add_argument("--slug", metavar="SLUG", help="Process only this aroma card slug")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, force=args.force, slug_filter=args.slug))


if __name__ == "__main__":
    main()
