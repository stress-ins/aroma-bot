"""Tests: curated oil reflection questions must never be overwritten or lost."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SEED_PATH = Path("data/reference_cards_seed.json")
PATCH_PATH = Path("data/oil_questions_patch.json")

# The 18 manually curated oils — these questions were provided by an expert
# and must NEVER be replaced with stubs or AI-generated text.
CURATED_SLUGS = {
    "orange", "basil", "bergamot", "helichrysum", "vetiver", "clove",
    "geranium", "grapefruit", "jasmine", "ylang-ylang", "ginger",
    "cedarwood", "cypress", "copaiba", "cinnamon", "lavender",
    "frankincense", "lime",
}

# Key phrases that MUST appear in each oil's questions (canary checks)
CURATED_CANARIES: dict[str, str] = {
    "orange": "радости",
    "basil": "ясности",
    "bergamot": "изменений",
    "helichrysum": "хождение по кругу",
    "vetiver": "самореализовываться",
    "clove": "ХОЧУ или ДОЛЖЕН",
    "geranium": "уязвимой",
    "grapefruit": "дискомфорта",
    "jasmine": "за что вас любят",
    "ylang-ylang": "контроль",
    "ginger": "не перевариваете",
    "cedarwood": "отцом",
    "cypress": "предвидели",
    "copaiba": "заложником",
    "cinnamon": "яркости",
    "lavender": "мамой",
    "frankincense": "центрированным",
    "lime": "серьёзно",
}

STUB_MARKER = "Какая тема этого масла"


class TestCuratedQuestionsInSeed:
    """Curated expert questions must be present in the seed file."""

    def test_seed_file_exists(self):
        assert SEED_PATH.exists()

    def test_all_curated_oils_have_questions_in_seed(self):
        cards = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        oil_map = {c["slug"]: c for c in cards if c.get("category") == "aroma"}

        for slug in CURATED_SLUGS:
            assert slug in oil_map, f"Oil {slug} missing from seed"
            questions = oil_map[slug].get("payload", {}).get("questions", "")
            assert questions, f"Oil {slug} has empty questions"
            assert len(questions) > 30, f"Oil {slug} questions too short: {questions[:50]}"

    def test_curated_questions_are_not_stubs(self):
        """Curated questions must NOT contain the generic stub text."""
        cards = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        oil_map = {c["slug"]: c for c in cards if c.get("category") == "aroma"}

        for slug in CURATED_SLUGS:
            questions = oil_map[slug].get("payload", {}).get("questions", "")
            assert STUB_MARKER not in questions, (
                f"Oil {slug} still has stub questions — must use expert-curated text"
            )

    def test_canary_phrases_present(self):
        """Each curated oil must contain its signature phrase."""
        cards = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        oil_map = {c["slug"]: c for c in cards if c.get("category") == "aroma"}

        for slug, canary in CURATED_CANARIES.items():
            questions = oil_map[slug].get("payload", {}).get("questions", "")
            assert canary in questions, (
                f"Oil {slug}: canary phrase '{canary}' not found in questions. "
                f"Expert-curated text may have been overwritten!"
            )


class TestPatchFileIntegrity:
    """The patch JSON must match the seed exactly for curated oils."""

    def test_patch_file_exists(self):
        assert PATCH_PATH.exists()

    def test_patch_has_all_curated_slugs(self):
        patch = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
        for slug in CURATED_SLUGS:
            assert slug in patch["questions"], f"Oil {slug} missing from patch file"

    def test_patch_matches_seed(self):
        """Patch file and seed must have identical questions for curated oils."""
        patch = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
        cards = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        oil_map = {c["slug"]: c for c in cards if c.get("category") == "aroma"}

        for slug in CURATED_SLUGS:
            patch_q = patch["questions"][slug]
            seed_q = oil_map[slug].get("payload", {}).get("questions", "")
            assert patch_q == seed_q, (
                f"Oil {slug}: patch and seed questions diverged!\n"
                f"Patch: {patch_q[:80]}\nSeed:  {seed_q[:80]}"
            )


class TestNoStubQuestions:
    """No oil in the seed should have the generic stub questions."""

    def test_no_stubs_in_seed(self):
        cards = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        oils = [c for c in cards if c.get("category") == "aroma"]
        stubs = []
        for oil in oils:
            q = oil.get("payload", {}).get("questions", "")
            if STUB_MARKER in q:
                stubs.append(oil["slug"])
        assert not stubs, f"Oils still have stub questions: {stubs}"


class TestPatchScriptIdempotency:
    """patch_oil_questions.py must not overwrite non-empty questions without --force."""

    def test_patch_script_exists(self):
        assert Path("scripts/patch_oil_questions.py").exists()

    def test_patch_script_has_force_flag(self):
        code = Path("scripts/patch_oil_questions.py").read_text()
        assert "--force" in code, "Patch script must support --force flag for safety"
        assert "existing" in code.lower() or "skip" in code.lower(), (
            "Patch script must check for existing questions before overwriting"
        )
