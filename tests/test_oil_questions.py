"""Tests: curated oil reflection questions must never be overwritten or lost."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SEED_PATH = Path("data/reference_cards_seed.json")
PATCH_PATH = Path("data/oil_questions_patch.json")

# Oils present in the seed file (43 oils)
SEED_SLUGS = {
    "orange", "basil", "bergamot", "helichrysum", "vetiver", "clove",
    "geranium", "grapefruit", "jasmine", "ylang-ylang", "ginger",
    "cedarwood", "cypress", "copaiba", "cinnamon", "lavender",
    "frankincense", "lime",
    "mandarin", "lemongrass", "clary-sage", "german-chamomile", "cassia",
    "spruce", "blue-spruce", "balsam-fir", "kunzea", "citronella",
    "black-pepper", "eucalyptus-globulus", "fennel", "juniper", "lemon",
    "marjoram", "neroli", "oregano", "patchouli", "peppermint",
    "rose", "rosemary", "sandalwood", "tea-tree", "thyme",
}

# All 74 oils with curated questions in the patch file.
# Includes seed oils + 31 DB-only oils (imported from PDF).
ALL_PATCH_SLUGS = SEED_SLUGS | {
    "bay-laurel", "benzoin", "black-spruce", "fragonia", "ho-wood",
    "myrrh", "pink-pepper", "angelica", "blue-tansy", "caraway",
    "carrot-seed", "cistus", "davana", "dill", "elemi",
    "eucaliptus-blue", "hong-kuai", "laurus", "ledum", "manuka",
    "melissa", "myrtle", "palmarosa", "palo-santo", "petitgrain",
    "ravintsara", "roman-chamomile", "sacred-frankincense", "spearmint",
    "valerian", "wintergreen",
}

# Key phrases that MUST appear in each oil's questions (canary checks).
# Checked against patch file (covers all 74 oils).
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
    "mandarin": "внутренним ребёнком",
    "lemongrass": "отпустить",
    "clary-sage": "интуиции",
    "german-chamomile": "мелочи выводят",
    "cassia": "страх мешает",
    "spruce": "внутренняя опора",
    "blue-spruce": "внутренняя опора",
    "balsam-fir": "ощущение «дома»",
    "kunzea": "эмоциональная боль",
    "citronella": "перезагрузка",
    "black-pepper": "сравниваете себя",
    "eucalyptus-globulus": "границы нарушают",
    "fennel": "куража",
    "juniper": "подавленный гнев",
    "lemon": "любопытство",
    "marjoram": "принять себя",
    "neroli": "тревога без видимой",
    "oregano": "привязаны настолько",
    "patchouli": "свою ценность",
    "peppermint": "общий язык",
    "rose": "рана, которая",
    "rosemary": "за рутиной",
    "sandalwood": "отпустить контроль",
    "tea-tree": "разрушают вас",
    "thyme": "силы воли",
    "bay-laurel": "заявлять о себе",
    "benzoin": "безусловную любовь",
    "black-spruce": "от намерения к действию",
    "fragonia": "женственностью",
    "ho-wood": "простить",
    "myrrh": "творить и выражать",
    "pink-pepper": "насмешек",
    "angelica": "корнями",
    "blue-tansy": "накопленный гнев",
    "caraway": "непереваренными",
    "carrot-seed": "Заботитесь ли вы о себе",
    "cistus": "не зажила",
    "davana": "адаптироваться",
    "dill": "навалилось сразу",
    "elemi": "с чистого листа",
    "eucaliptus-blue": "не хватает воздуха",
    "hong-kuai": "в центре собственной жизни",
    "laurus": "побеждать",
    "ledum": "застарелый гнев",
    "manuka": "стойкость",
    "melissa": "бережном внимании",
    "myrtle": "слова любви",
    "palmarosa": "эмоционально защищённым",
    "palo-santo": "священным",
    "petitgrain": "внутренний диалог",
    "ravintsara": "продышаться",
    "roman-chamomile": "терпения",
    "sacred-frankincense": "превосходит слова",
    "spearmint": "лёгкость и игривость",
    "valerian": "заснуть ночью",
    "wintergreen": "сопротивляться",
}

STUB_MARKER = "Какая тема этого масла"


class TestCuratedQuestionsInSeed:
    """Curated expert questions must be present in the seed file (43 oils)."""

    def test_seed_file_exists(self):
        assert SEED_PATH.exists()

    def test_all_seed_oils_have_questions(self):
        cards = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        oil_map = {c["slug"]: c for c in cards if c.get("category") == "aroma"}

        for slug in SEED_SLUGS:
            assert slug in oil_map, f"Oil {slug} missing from seed"
            questions = oil_map[slug].get("payload", {}).get("questions", "")
            assert questions, f"Oil {slug} has empty questions"
            assert len(questions) > 30, f"Oil {slug} questions too short: {questions[:50]}"

    def test_curated_questions_are_not_stubs(self):
        """Curated questions must NOT contain the generic stub text."""
        cards = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        oil_map = {c["slug"]: c for c in cards if c.get("category") == "aroma"}

        for slug in SEED_SLUGS:
            questions = oil_map[slug].get("payload", {}).get("questions", "")
            assert STUB_MARKER not in questions, (
                f"Oil {slug} still has stub questions — must use expert-curated text"
            )

    def test_seed_canary_phrases_present(self):
        """Each seed oil must contain its signature phrase."""
        cards = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        oil_map = {c["slug"]: c for c in cards if c.get("category") == "aroma"}

        for slug in SEED_SLUGS:
            canary = CURATED_CANARIES.get(slug)
            if not canary:
                continue
            questions = oil_map[slug].get("payload", {}).get("questions", "")
            assert canary in questions, (
                f"Oil {slug}: canary phrase '{canary}' not found in questions. "
                f"Expert-curated text may have been overwritten!"
            )


class TestPatchFileIntegrity:
    """The patch JSON must cover all 74 oils with correct canary phrases."""

    def test_patch_file_exists(self):
        assert PATCH_PATH.exists()

    def test_patch_has_all_slugs(self):
        patch = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
        for slug in ALL_PATCH_SLUGS:
            assert slug in patch["questions"], f"Oil {slug} missing from patch file"

    def test_patch_canary_phrases(self):
        """Each oil in the patch must contain its canary phrase."""
        patch = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
        for slug, canary in CURATED_CANARIES.items():
            questions = patch["questions"].get(slug, "")
            assert canary in questions, (
                f"Oil {slug}: canary phrase '{canary}' not found in patch questions"
            )

    def test_patch_matches_seed_for_seed_oils(self):
        """Patch file and seed must have identical questions for seed oils."""
        patch = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
        cards = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        oil_map = {c["slug"]: c for c in cards if c.get("category") == "aroma"}

        for slug in SEED_SLUGS:
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

    def test_no_stubs_in_patch(self):
        patch = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
        stubs = [s for s, q in patch["questions"].items() if STUB_MARKER in q]
        assert not stubs, f"Patch has stub questions: {stubs}"


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
