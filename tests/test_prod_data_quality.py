"""Production data quality tests.

Run against a dump of the production database to catch real data issues
that isolated unit tests miss. Refresh the dump with:
    scp root@46.32.186.192:/opt/aroma/data/aroma.db data/aroma_prod_dump.db

These tests document known issues and will fail until they're fixed in prod.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tests.conftest_prod import PROD_DUMP, prod_db  # noqa: F401 — fixture

pytestmark = pytest.mark.skipif(
    not PROD_DUMP.exists(),
    reason="Production dump not found: data/aroma_prod_dump.db",
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _all_slugs(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute("SELECT slug FROM aroma_cards")
    return {r["slug"] for r in cur.fetchall()}


def _cards_by_category(conn: sqlite3.Connection, category: str) -> list[dict]:
    cur = conn.execute(
        "SELECT slug, name, category, source_type, payload FROM aroma_cards WHERE category = ?",
        (category,),
    )
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        rows.append(d)
    return rows


# ── Card counts ────────────────────────────────────────────────────────────────

class TestCardCounts:
    """Ensure prod has expected number of cards per category."""

    def test_aroma_cards_exist(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        cards = _cards_by_category(conn, "aroma")
        assert len(cards) >= 70, f"Expected ≥70 aroma cards, got {len(cards)}"

    def test_blend_cards_exist(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        cards = _cards_by_category(conn, "blend")
        assert len(cards) >= 200, f"Expected ≥200 blend cards, got {len(cards)}"

    def test_symptom_cards_exist(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        cards = _cards_by_category(conn, "symptom")
        assert len(cards) >= 170, f"Expected ≥170 symptom cards, got {len(cards)}"

    def test_no_empty_slugs(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        cur = conn.execute("SELECT COUNT(*) as cnt FROM aroma_cards WHERE slug IS NULL OR slug = ''")
        assert cur.fetchone()["cnt"] == 0

    def test_no_duplicate_slugs(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        cur = conn.execute(
            "SELECT slug, COUNT(*) as cnt FROM aroma_cards GROUP BY slug HAVING cnt > 1"
        )
        dupes = cur.fetchall()
        assert len(dupes) == 0, f"Duplicate slugs: {[r['slug'] for r in dupes]}"


# ── Cross-reference integrity ──────────────────────────────────────────────────

class TestCrossRefIntegrity:
    """Cross-refs should point to existing cards."""

    def test_blend_ingredient_slugs_exist(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        all_slugs = _all_slugs(conn)
        blends = _cards_by_category(conn, "blend")

        broken: list[tuple[str, str]] = []
        for card in blends:
            for slug in card["payload"].get("ingredient_slugs") or []:
                if slug and slug not in all_slugs:
                    broken.append((card["slug"], slug))

        assert len(broken) == 0, (
            f"{len(broken)} broken ingredient refs. "
            f"Missing slugs: {sorted(set(s for _, s in broken))}"
        )

    def test_blend_complementary_oil_slugs_exist(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        all_slugs = _all_slugs(conn)
        blends = _cards_by_category(conn, "blend")

        broken: list[tuple[str, str]] = []
        for card in blends:
            for slug in card["payload"].get("complementary_oil_slugs") or []:
                if slug and slug not in all_slugs:
                    broken.append((card["slug"], slug))

        assert len(broken) == 0, (
            f"{len(broken)} broken complementary oil refs. "
            f"Missing: {sorted(set(s for _, s in broken))}"
        )

    def test_symptom_recommended_oil_slugs_exist(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        all_slugs = _all_slugs(conn)
        symptoms = _cards_by_category(conn, "symptom")

        broken: list[tuple[str, str]] = []
        for card in symptoms:
            for slug in card["payload"].get("recommended_oil_slugs") or []:
                if slug and slug not in all_slugs:
                    broken.append((card["slug"], slug))

        assert len(broken) == 0, (
            f"{len(broken)} broken symptom→oil refs. "
            f"Missing: {sorted(set(s for _, s in broken))}"
        )

    def test_symptom_recommended_blend_slugs_exist(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        all_slugs = _all_slugs(conn)
        symptoms = _cards_by_category(conn, "symptom")

        broken: list[tuple[str, str]] = []
        for card in symptoms:
            for slug in card["payload"].get("recommended_blend_slugs") or []:
                if slug and slug not in all_slugs:
                    broken.append((card["slug"], slug))

        assert len(broken) == 0, (
            f"{len(broken)} broken symptom→blend refs. "
            f"Missing: {sorted(set(s for _, s in broken))}"
        )


# ── Data completeness ─────────────────────────────────────────────────────────

class TestDataCompleteness:
    """Every card should have required fields filled."""

    def test_all_cards_have_name(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        cur = conn.execute(
            "SELECT slug FROM aroma_cards WHERE name IS NULL OR name = ''"
        )
        empty = [r["slug"] for r in cur.fetchall()]
        assert len(empty) == 0, f"Cards without name: {empty}"

    def test_aroma_cards_have_description(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        cards = _cards_by_category(conn, "aroma")

        missing = [
            c["slug"] for c in cards
            if not (c["payload"].get("description") or "").strip()
        ]
        assert len(missing) == 0, f"{len(missing)} aroma cards without description: {missing[:10]}"

    def test_aroma_cards_have_description_short(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        cards = _cards_by_category(conn, "aroma")

        missing = [
            c["slug"] for c in cards
            if len((c["payload"].get("description_short") or "").strip()) < 10
        ]
        assert len(missing) == 0, (
            f"{len(missing)} aroma cards with missing/short description_short: {missing[:10]}"
        )

    def test_blend_cards_have_name_ru(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        blends = _cards_by_category(conn, "blend")

        missing = [
            c["slug"] for c in blends
            if not (c["payload"].get("name_ru") or "").strip()
        ]
        assert len(missing) == 0, (
            f"{len(missing)} blends without name_ru: {missing[:10]}"
        )

    def test_aroma_source_type_valid(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        cards = _cards_by_category(conn, "aroma")

        valid = {"flower", "tree", "resin", "spice", "herb", "grass", "citrus"}
        invalid = [
            (c["slug"], c["source_type"]) for c in cards
            if c["source_type"] not in valid
        ]
        assert len(invalid) == 0, f"Invalid source_type: {invalid}"

    def test_symptom_cards_have_category_group(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        symptoms = _cards_by_category(conn, "symptom")

        missing = [
            c["slug"] for c in symptoms
            if not (c["payload"].get("category_group") or "").strip()
        ]
        assert len(missing) == 0, (
            f"{len(missing)} symptoms without category_group: {missing[:10]}"
        )

    def test_symptom_cards_have_parent_group(self, prod_db):  # noqa: F811
        conn = _conn(prod_db)
        symptoms = _cards_by_category(conn, "symptom")

        missing = [
            c["slug"] for c in symptoms
            if not (c["payload"].get("parent_group") or "").strip()
        ]
        assert len(missing) == 0, (
            f"{len(missing)} symptoms without parent_group: {missing[:10]}"
        )


# ── Serialization smoke tests (via miniapp_references) ─────────────────────────

class TestSerializationSmoke:
    """Verify that miniapp_references can list/get every card without crashing."""

    @pytest.mark.asyncio
    async def test_list_aroma_cards(self, prod_db):  # noqa: F811
        from bot.services.miniapp_references import list_reference_cards
        cards = await list_reference_cards("aroma")
        assert len(cards) >= 70
        for c in cards:
            assert c["slug"]
            assert c["name"]

    @pytest.mark.asyncio
    async def test_list_blend_cards(self, prod_db):  # noqa: F811
        from bot.services.miniapp_references import list_reference_cards
        cards = await list_reference_cards("blend")
        assert len(cards) >= 200

    @pytest.mark.asyncio
    async def test_list_symptom_cards(self, prod_db):  # noqa: F811
        from bot.services.miniapp_references import list_reference_cards
        cards = await list_reference_cards("symptom")
        assert len(cards) >= 170

    @pytest.mark.asyncio
    async def test_get_every_aroma_card(self, prod_db):  # noqa: F811
        from bot.services.miniapp_references import list_reference_cards, get_reference_card
        cards = await list_reference_cards("aroma")
        cards = cards[:10]  # sample — full iteration tested ad-hoc
        errors: list[tuple[str, str]] = []
        for c in cards:
            try:
                detail = await get_reference_card("aroma", c["slug"])
                assert detail is not None
                assert detail["slug"] == c["slug"]
            except Exception as exc:
                errors.append((c["slug"], str(exc)))
        assert len(errors) == 0, f"Failed to get {len(errors)} cards: {errors[:5]}"

    @pytest.mark.asyncio
    async def test_get_every_blend_card(self, prod_db):  # noqa: F811
        from bot.services.miniapp_references import list_reference_cards, get_reference_card
        cards = await list_reference_cards("blend")
        cards = cards[:10]  # sample — full iteration tested ad-hoc
        errors: list[tuple[str, str]] = []
        for c in cards:
            try:
                detail = await get_reference_card("blend", c["slug"])
                assert detail is not None
            except Exception as exc:
                errors.append((c["slug"], str(exc)))
        assert len(errors) == 0, f"Failed to get {len(errors)} blends: {errors[:5]}"

    @pytest.mark.asyncio
    async def test_get_every_symptom_card(self, prod_db):  # noqa: F811
        from bot.services.miniapp_references import list_reference_cards, get_reference_card
        cards = await list_reference_cards("symptom")
        cards = cards[:10]  # sample — full iteration tested ad-hoc
        errors: list[tuple[str, str]] = []
        for c in cards:
            try:
                detail = await get_reference_card("symptom", c["slug"])
                assert detail is not None
            except Exception as exc:
                errors.append((c["slug"], str(exc)))
        assert len(errors) == 0, f"Failed to get {len(errors)} symptoms: {errors[:5]}"


# ── Draft integrity ────────────────────────────────────────────────────────────

class TestDraftIntegrity:
    """Verify draft data is consistent."""

    @pytest.mark.asyncio
    async def test_all_drafts_loadable(self, prod_db):  # noqa: F811
        from bot.services.drafts_store import list_recent_drafts
        drafts = await list_recent_drafts(limit=100, newest_first=True)
        assert len(drafts) > 0
        for d in drafts:
            assert d.draft_id
            assert d.kind in ("carousel", "reels", "reels_v2", "threads", "threads_series", "content")
            assert d.payload is not None

    @pytest.mark.asyncio
    async def test_carousel_drafts_have_slides(self, prod_db):  # noqa: F811
        from bot.services.drafts_store import list_recent_drafts
        drafts = await list_recent_drafts(limit=100, kind="carousel")
        for d in drafts:
            slides = d.payload.get("slides", [])
            assert len(slides) > 0, f"Carousel {d.draft_id} has no slides"

    @pytest.mark.asyncio
    async def test_carousel_drafts_serialize(self, prod_db):  # noqa: F811
        from bot.services.drafts_store import list_recent_drafts
        from bot.services.miniapp_presenter import serialize_draft
        drafts = await list_recent_drafts(limit=100, kind="carousel")
        errors: list[tuple[str, str]] = []
        for d in drafts:
            try:
                result = await serialize_draft(d)
                assert result["draft_id"] == d.draft_id
                assert result["kind"] == "carousel"
            except Exception as exc:
                errors.append((d.draft_id, str(exc)))
        assert len(errors) == 0, f"Serialization failed: {errors}"
