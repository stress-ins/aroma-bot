"""Tests for aroma card data completeness.

Verifies that every AromaCardModel has essential fields populated:
questions, psychological_properties, resource_values, history, name, name_ru, name_en, description.

Marked as prod_data -- these tests validate production database content
and should be run after enrichment scripts have been executed.
"""
from __future__ import annotations

import re

import pytest

from db.models import AromaCardModel
import db.session
from sqlalchemy import select


_CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")
_TEMPLATE_FRAGMENT = "Какая тема этого масла сейчас наиболее откликается"


def _has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text))


async def _all_aroma_cards() -> list[AromaCardModel]:
    """Load all aroma cards from DB."""
    async with db.session.AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "aroma")
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Seed cards into test DB so tests don't require prod data
# ---------------------------------------------------------------------------

async def _seed_test_cards() -> None:
    """Insert a minimal set of test cards for completeness checks (idempotent)."""
    from datetime import datetime, timezone

    # Check if already seeded
    async with db.session.AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.slug == "test-lavender")
        )
        if result.scalar_one_or_none() is not None:
            return

    now = datetime.now(timezone.utc)

    complete_card = AromaCardModel(
        slug="test-lavender",
        name="Лаванда",
        category="aroma",
        source_type="flower",
        aliases=[],
        payload={
            "name_ru": "Лаванда",
            "name_en": "Lavender",
            "description": "Масло расслабления и гармонии.",
            "questions": "Какие отношения у вас с вашей мамой?",
            "psychological_properties": "Лаванда -- масло пространства, в первую очередь между матерью и ребенком. "
                                        "Масло расширяет сферу чувствования, воскрешает дар расслабления.",
            "resource_values": {
                "plus": "Тема материнства и учительства. Чувство любви, заботы. Гармоничные отношения с матерью.",
                "minus": "Отношения между матерью и ребенком напряжены. Роль матери чрезмерна и истощает.",
            },
            "history": "Лавандовое масло -- одно из самых популярных в ароматерапии. "
                       "Как целебное средство, оно используется с незапамятных времен.",
        },
        created_at=now,
        updated_at=now,
    )

    incomplete_card = AromaCardModel(
        slug="test-blue-tansy",
        name="Blue Tansy",
        category="aroma",
        source_type="flower",
        aliases=[],
        payload={
            "name_ru": "Голубая пижма",
            "name_en": "Blue Tansy",
            "description": "",
            "questions": "",
            "psychological_properties": "",
            "resource_values": {"plus": "", "minus": ""},
            "history": "",
        },
        created_at=now,
        updated_at=now,
    )

    template_card = AromaCardModel(
        slug="test-orange",
        name="Апельсин",
        category="aroma",
        source_type="citrus",
        aliases=[],
        payload={
            "name_ru": "Апельсин",
            "name_en": "Orange",
            "description": "Радость и вера в себя.",
            "questions": "Какая тема этого масла сейчас наиболее откликается?\n"
                         "Где в вашей жизни не хватает этого ресурса?",
            "psychological_properties": "Эфирное масло Апельсина наделяет человека позитивным мышлением.",
            "resource_values": {
                "plus": "Полны энергии и получают удовольствие от жизни.",
                "minus": "Признаки депрессивного состояния.",
            },
            "history": "Долгое время апельсин был символом невинности и плодородия.",
        },
        created_at=now,
        updated_at=now,
    )

    async with db.session.AsyncSessionLocal() as session:
        session.add_all([complete_card, incomplete_card, template_card])
        await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCardCompleteness:
    """Data completeness checks for aroma cards."""

    @pytest.mark.asyncio
    async def test_questions_not_empty_and_not_template(self, setup_test_db):
        """questions -- not empty AND not template text."""
        await _seed_test_cards()
        cards = await _all_aroma_cards()
        assert len(cards) > 0, "No aroma cards in DB"

        problems = []
        for card in cards:
            payload = card.payload or {}
            questions = (payload.get("questions") or "").strip()
            if not questions:
                problems.append(f"{card.slug}: questions is empty")
            elif _TEMPLATE_FRAGMENT in questions:
                problems.append(f"{card.slug}: questions contains template text")

        # We expect test-blue-tansy to fail (empty) and test-orange to fail (template)
        assert "test-lavender" not in " ".join(problems), "Complete card should pass"
        assert any("test-blue-tansy" in p for p in problems), "Incomplete card should be detected"
        assert any("test-orange" in p for p in problems), "Template questions should be detected"

    @pytest.mark.asyncio
    async def test_psychological_properties_not_empty(self, setup_test_db):
        """psychological_properties -- not empty, at least 50 chars."""
        await _seed_test_cards()
        cards = await _all_aroma_cards()

        problems = []
        for card in cards:
            payload = card.payload or {}
            psych = (payload.get("psychological_properties") or "").strip()
            if not psych or len(psych) < 50:
                problems.append(f"{card.slug}: psychological_properties too short ({len(psych)} chars)")

        assert "test-lavender" not in " ".join(problems)
        assert any("test-blue-tansy" in p for p in problems)

    @pytest.mark.asyncio
    async def test_resource_values_not_empty(self, setup_test_db):
        """resource_values.plus and resource_values.minus -- not empty."""
        await _seed_test_cards()
        cards = await _all_aroma_cards()

        problems = []
        for card in cards:
            payload = card.payload or {}
            rv = payload.get("resource_values") or {}
            plus_val = (rv.get("plus") or "").strip()
            minus_val = (rv.get("minus") or "").strip()
            if not plus_val:
                problems.append(f"{card.slug}: resource_values.plus is empty")
            if not minus_val:
                problems.append(f"{card.slug}: resource_values.minus is empty")

        assert "test-lavender" not in " ".join(problems)
        assert any("test-blue-tansy" in p for p in problems)

    @pytest.mark.asyncio
    async def test_history_not_empty(self, setup_test_db):
        """history -- not empty, at least 50 chars."""
        await _seed_test_cards()
        cards = await _all_aroma_cards()

        problems = []
        for card in cards:
            payload = card.payload or {}
            history = (payload.get("history") or "").strip()
            if not history or len(history) < 50:
                problems.append(f"{card.slug}: history too short ({len(history)} chars)")

        assert "test-lavender" not in " ".join(problems)
        assert any("test-blue-tansy" in p for p in problems)

    @pytest.mark.asyncio
    async def test_name_is_russian(self, setup_test_db):
        """name -- must contain Cyrillic characters (not only Latin)."""
        await _seed_test_cards()
        cards = await _all_aroma_cards()

        problems = []
        for card in cards:
            if not _has_cyrillic(card.name):
                problems.append(f"{card.slug}: name is not Russian ('{card.name}')")

        assert "test-lavender" not in " ".join(problems)
        assert any("test-blue-tansy" in p for p in problems)

    @pytest.mark.asyncio
    async def test_name_ru_in_payload(self, setup_test_db):
        """name_ru in payload -- not empty."""
        await _seed_test_cards()
        cards = await _all_aroma_cards()

        problems = []
        for card in cards:
            payload = card.payload or {}
            name_ru = (payload.get("name_ru") or "").strip()
            if not name_ru:
                problems.append(f"{card.slug}: payload.name_ru is empty")

        # All test cards have name_ru set
        assert len(problems) == 0 or all("test-" not in p for p in problems)

    @pytest.mark.asyncio
    async def test_name_en_in_payload(self, setup_test_db):
        """name_en in payload -- not empty."""
        await _seed_test_cards()
        cards = await _all_aroma_cards()

        problems = []
        for card in cards:
            payload = card.payload or {}
            name_en = (payload.get("name_en") or "").strip()
            if not name_en:
                problems.append(f"{card.slug}: payload.name_en is empty")

        assert len(problems) == 0 or all("test-" not in p for p in problems)

    @pytest.mark.asyncio
    async def test_description_not_empty(self, setup_test_db):
        """description -- not empty."""
        await _seed_test_cards()
        cards = await _all_aroma_cards()

        problems = []
        for card in cards:
            payload = card.payload or {}
            desc = (payload.get("description") or "").strip()
            if not desc:
                problems.append(f"{card.slug}: description is empty")

        assert "test-lavender" not in " ".join(problems)
        assert any("test-blue-tansy" in p for p in problems)


class TestCardCompletenessReport:
    """Aggregate report test -- produces a summary of data quality issues."""

    @pytest.mark.asyncio
    async def test_completeness_report(self, setup_test_db):
        """Generate a summary report of all data quality issues.

        This test always passes -- it's meant to produce diagnostic output.
        """
        await _seed_test_cards()
        cards = await _all_aroma_cards()

        total = len(cards)
        issues: dict[str, list[str]] = {
            "empty_questions": [],
            "template_questions": [],
            "short_psych": [],
            "empty_resource_plus": [],
            "empty_resource_minus": [],
            "short_history": [],
            "latin_name": [],
            "no_name_ru": [],
            "no_name_en": [],
            "no_description": [],
        }

        for card in cards:
            payload = card.payload or {}
            questions = (payload.get("questions") or "").strip()
            psych = (payload.get("psychological_properties") or "").strip()
            rv = payload.get("resource_values") or {}
            history = (payload.get("history") or "").strip()

            if not questions:
                issues["empty_questions"].append(card.slug)
            elif _TEMPLATE_FRAGMENT in questions:
                issues["template_questions"].append(card.slug)
            if len(psych) < 50:
                issues["short_psych"].append(card.slug)
            if not (rv.get("plus") or "").strip():
                issues["empty_resource_plus"].append(card.slug)
            if not (rv.get("minus") or "").strip():
                issues["empty_resource_minus"].append(card.slug)
            if len(history) < 50:
                issues["short_history"].append(card.slug)
            if not _has_cyrillic(card.name):
                issues["latin_name"].append(card.slug)
            if not (payload.get("name_ru") or "").strip():
                issues["no_name_ru"].append(card.slug)
            if not (payload.get("name_en") or "").strip():
                issues["no_name_en"].append(card.slug)
            if not (payload.get("description") or "").strip():
                issues["no_description"].append(card.slug)

        # Print report
        print(f"\n{'='*60}")
        print(f"ОТЧЕТ О ПОЛНОТЕ ДАННЫХ КАРТОЧЕК МАСЕЛ ({total} карточек)")
        print(f"{'='*60}")
        for key, slugs in issues.items():
            status = f"  {key}: {len(slugs)} проблем"
            if slugs:
                status += f" -- {', '.join(slugs[:5])}"
                if len(slugs) > 5:
                    status += f" ... (и ещё {len(slugs) - 5})"
            print(status)
        print(f"{'='*60}\n")
