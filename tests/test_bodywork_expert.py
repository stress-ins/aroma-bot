"""Tests for bodywork_expert and sound_healing_expert agents."""
import pytest


# ── Bodywork Expert ─────────────────────────────────────────────────

class TestBodyworkExpert:
    """Rule-based verification for massage/osteo/biodynamics cards."""

    def test_valid_massage_card_passes(self):
        from bot.agents.bodywork_expert import _basic_verify

        card = {
            "source_type": "classical",
            "payload": {
                "therapeutic_properties": "Снятие мышечного напряжения, улучшение кровообращения",
                "contraindications": "тромбоз, онкология, острое воспаление, лихорадка, беременность (1 триместр)",
                "description": "Классический массаж всего тела",
                "session_duration": "60 мин",
                "pressure_level": "среднее",
                "difficulty_level": "начинающий",
            },
        }
        score, issues, _ = _basic_verify(card, "massage")
        assert score >= 0.7
        assert len(issues) == 0

    def test_missing_contraindications_penalized(self):
        from bot.agents.bodywork_expert import _basic_verify

        card = {
            "source_type": "deep_tissue",
            "payload": {
                "therapeutic_properties": "Глубокая проработка мышц",
                "description": "Глубокотканный массаж",
                "session_duration": "45 мин",
            },
        }
        score, issues, _ = _basic_verify(card, "massage")
        assert score < 1.0
        assert any("contraindications" in i for i in issues)

    def test_unknown_source_type_penalized(self):
        from bot.agents.bodywork_expert import _basic_verify

        card = {
            "source_type": "quantum_healing",
            "payload": {
                "therapeutic_properties": "test",
                "contraindications": "тромбоз, онкология, острое воспаление, лихорадка",
                "description": "test",
                "session_duration": "30 мин",
            },
        }
        score, issues, _ = _basic_verify(card, "massage")
        assert any("source_type" in i for i in issues)

    def test_missing_critical_contraindications_flagged(self):
        from bot.agents.bodywork_expert import _basic_verify

        card = {
            "source_type": "classical",
            "payload": {
                "therapeutic_properties": "Релаксация",
                "contraindications": "аллергия на масла",
                "description": "Массаж",
                "session_duration": "60 мин",
            },
        }
        score, issues, _ = _basic_verify(card, "massage")
        assert any("critical items" in i for i in issues)

    def test_osteo_category(self):
        from bot.agents.bodywork_expert import _basic_verify

        card = {
            "source_type": "craniosacral",
            "payload": {
                "therapeutic_properties": "Балансировка краниосакрального ритма",
                "contraindications": "тромбоз, онкология, аневризма, острый инсульт",
                "description": "Краниосакральная терапия",
                "session_duration": "50 мин",
                "pressure_level": "лёгкое",
            },
        }
        score, issues, _ = _basic_verify(card, "osteo")
        assert score >= 0.7

    def test_unsupported_category_rejected(self):
        from bot.agents.bodywork_expert import verify_bodywork_content

        result = pytest.get_event_loop = None  # noqa
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            verify_bodywork_content({"source_type": "test"}, "yoga", dry_run=True)
        )
        assert result["passed"] is False
        assert "unsupported" in result["issues"][0]


# ── Sound Healing Expert ────────────────────────────────────────────

class TestSoundHealingExpert:
    """Rule-based verification for sound healing cards."""

    def test_valid_gong_card_passes(self):
        from bot.agents.sound_healing_expert import _basic_verify

        card = {
            "source_type": "planetary_gong",
            "payload": {
                "therapeutic_properties": "Глубокая релаксация, снятие напряжения",
                "contraindications": "эпилепсия, беременность, кардиостимулятор, острые психические расстройства",
                "description": "Планетарный гонг Paiste Planet",
                "session_duration": "45 мин",
                "frequency_range": "80-200 Hz",
            },
        }
        score, issues, _ = _basic_verify(card)
        assert score >= 0.7
        assert len(issues) == 0

    def test_gong_missing_contraindications_penalized(self):
        from bot.agents.sound_healing_expert import _basic_verify

        card = {
            "source_type": "planetary_gong",
            "payload": {
                "therapeutic_properties": "Глубокая релаксация",
                "description": "Гонг",
                "session_duration": "45 мин",
            },
        }
        score, issues, _ = _basic_verify(card)
        assert score < 1.0
        assert any("contraindications" in i for i in issues)

    def test_gong_missing_critical_items_flagged(self):
        from bot.agents.sound_healing_expert import _basic_verify

        card = {
            "source_type": "gong",
            "payload": {
                "therapeutic_properties": "Релаксация",
                "contraindications": "индивидуальная непереносимость",
                "description": "Гонг-медитация",
                "session_duration": "60 мин",
            },
        }
        score, issues, _ = _basic_verify(card)
        assert any("critical" in i.lower() for i in issues)

    def test_singing_bowl_wants_note(self):
        from bot.agents.sound_healing_expert import _basic_verify

        card = {
            "source_type": "tibetan_singing_bowl",
            "payload": {
                "therapeutic_properties": "Медитация, гармонизация",
                "contraindications": "эпилепсия, острые психические расстройства, беременность, кардиостимулятор",
                "description": "Тибетская поющая чаша",
                "session_duration": "30 мин",
            },
        }
        score, issues, _ = _basic_verify(card)
        assert any("note" in i for i in issues)

    def test_binaural_duration_validated(self):
        from bot.agents.sound_healing_expert import _basic_verify

        card = {
            "source_type": "binaural_beats",
            "payload": {
                "therapeutic_properties": "Синхронизация полушарий",
                "contraindications": "эпилепсия, острые психические расстройства",
                "description": "Бинауральные ритмы",
                "session_duration": "30 мин",
                "frequency_range": "10 Hz",
            },
        }
        score, issues, _ = _basic_verify(card)
        assert score >= 0.7

    def test_unknown_sound_type_penalized(self):
        from bot.agents.sound_healing_expert import _basic_verify

        card = {
            "source_type": "quantum_resonance",
            "payload": {
                "therapeutic_properties": "test",
                "contraindications": "эпилепсия, острые психические расстройства",
                "description": "test",
            },
        }
        _, issues, _ = _basic_verify(card)
        assert any("source_type" in i for i in issues)


# ── Medical Reviewer bodywork integration ───────────────────────────

class TestMedicalReviewerBodywork:
    """Medical reviewer handles bodywork categories."""

    def test_massage_forbidden_claim_detected(self):
        from bot.agents.medical_reviewer import _rule_based_check

        card = {
            "category": "massage",
            "description": "Этот массаж лечит грыжу межпозвоночного диска",
        }
        score, issues, _ = _rule_based_check(card)
        assert any("CRITICAL" in i for i in issues)

    def test_massage_needs_precautions_flag(self):
        from bot.agents.medical_reviewer import _rule_based_check

        card = {
            "category": "massage",
            "description": "Классический массаж спины",
        }
        _, _, needs_llm = _rule_based_check(card)
        assert needs_llm is True

    def test_osteo_forbidden_claim_detected(self):
        from bot.agents.medical_reviewer import _rule_based_check

        card = {
            "category": "osteo",
            "description": "Остеопрактика вправляет позвонки на место",
        }
        score, issues, _ = _rule_based_check(card)
        assert any("CRITICAL" in i for i in issues)


# ── Reference Experts new categories ────────────────────────────────

class TestReferenceExpertsCategories:
    """Reference experts support bodywork and sound categories."""

    def test_massage_category_has_system_prompt(self):
        from bot.agents.reference_experts import _SYSTEM_BY_CATEGORY

        assert "massage" in _SYSTEM_BY_CATEGORY
        assert "массаж" in _SYSTEM_BY_CATEGORY["massage"].lower()

    def test_osteo_category_has_system_prompt(self):
        from bot.agents.reference_experts import _SYSTEM_BY_CATEGORY

        assert "osteo" in _SYSTEM_BY_CATEGORY
        assert "остеопат" in _SYSTEM_BY_CATEGORY["osteo"].lower() or "остеопракт" in _SYSTEM_BY_CATEGORY["osteo"].lower()

    def test_biodynamics_category_has_system_prompt(self):
        from bot.agents.reference_experts import _SYSTEM_BY_CATEGORY

        assert "biodynamics" in _SYSTEM_BY_CATEGORY

    def test_sound_category_mentions_gong(self):
        from bot.agents.reference_experts import _SYSTEM_BY_CATEGORY

        assert "гонг" in _SYSTEM_BY_CATEGORY["sound"].lower()
