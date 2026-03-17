"""Tests for bot.agents.blend_content_context."""
from __future__ import annotations

from bot.agents.blend_content_context import (
    build_blend_carousel_narrative,
    build_blend_reels_concept,
    build_blend_strategist_block,
    build_blend_writer_block,
    mood_to_visual_directive,
)

_SAMPLE_BC = {
    "title": "Смесь для концентрации",
    "brief": "фокус и ясность ума",
    "oils": [
        {"name_ru": "Розмарин", "name_en": "Rosemary", "drops": 3, "role": "основа"},
        {"name_ru": "Мята", "name_en": "Peppermint", "drops": 2, "role": "акцент"},
    ],
    "total_drops": 5,
    "profile": {"focus": 60, "energy": 20, "creativity": 10, "calm": 10},
    "expert_note": "Розмарин и мята дают яркий ментальный подъём",
    "application_guide": "2 капли в диффузор на 30 минут",
    "tags": ["концентрация", "работа"],
}


class TestBuildBlendStrategistBlock:
    def test_includes_title_and_brief(self):
        result = build_blend_strategist_block(_SAMPLE_BC)
        assert "Смесь для концентрации" in result
        assert "фокус и ясность ума" in result

    def test_includes_profile(self):
        result = build_blend_strategist_block(_SAMPLE_BC)
        assert "focus 60%" in result

    def test_includes_oils(self):
        result = build_blend_strategist_block(_SAMPLE_BC)
        assert "Розмарин" in result
        assert "Мята" in result

    def test_includes_tags(self):
        result = build_blend_strategist_block(_SAMPLE_BC)
        assert "концентрация" in result

    def test_empty_context(self):
        result = build_blend_strategist_block({})
        assert isinstance(result, str)


class TestBuildBlendWriterBlock:
    def test_includes_oils_with_drops(self):
        result = build_blend_writer_block(_SAMPLE_BC)
        assert "Розмарин" in result
        assert "3 кап." in result

    def test_includes_expert_note(self):
        result = build_blend_writer_block(_SAMPLE_BC)
        assert "ментальный подъём" in result

    def test_includes_application(self):
        result = build_blend_writer_block(_SAMPLE_BC)
        assert "диффузор" in result

    def test_enriches_with_oil_cards(self):
        oil_cards = [{"name": "Розмарин", "mind_effect": "стимулирует память", "therapeutic_properties": "анальгетик"}]
        result = build_blend_writer_block(_SAMPLE_BC, oil_cards=oil_cards)
        assert "стимулирует память" in result


class TestBuildBlendCarouselNarrative:
    def test_includes_title(self):
        result = build_blend_carousel_narrative(_SAMPLE_BC)
        assert "Смесь для концентрации" in result

    def test_includes_slide_structure(self):
        result = build_blend_carousel_narrative(_SAMPLE_BC)
        assert "Slide 1" in result
        assert "Slide 5" in result

    def test_includes_oil_names(self):
        result = build_blend_carousel_narrative(_SAMPLE_BC)
        assert "Розмарин" in result

    def test_dominant_trait(self):
        result = build_blend_carousel_narrative(_SAMPLE_BC)
        assert "концентрацию" in result  # focus is dominant


class TestBuildBlendReelsConcept:
    def test_includes_transformation_arc(self):
        result = build_blend_reels_concept(_SAMPLE_BC)
        assert "ДО" in result
        assert "ПОСЛЕ" in result

    def test_includes_oils(self):
        result = build_blend_reels_concept(_SAMPLE_BC)
        assert "Розмарин" in result


class TestMoodToVisualDirective:
    def test_focus_dominant(self):
        result = mood_to_visual_directive({"focus": 60, "energy": 30, "creativity": 5, "calm": 5})
        assert "amber" in result or "mint" in result

    def test_calm_dominant(self):
        result = mood_to_visual_directive({"focus": 5, "energy": 5, "creativity": 5, "calm": 85})
        assert "lavender" in result

    def test_creativity_dominant(self):
        result = mood_to_visual_directive({"focus": 5, "energy": 5, "creativity": 80, "calm": 10})
        assert "botanical" in result or "purple" in result

    def test_energy_dominant(self):
        result = mood_to_visual_directive({"focus": 5, "energy": 80, "creativity": 5, "calm": 10})
        assert "citrus" in result

    def test_empty_profile(self):
        result = mood_to_visual_directive({})
        assert result == ""

    def test_balanced(self):
        result = mood_to_visual_directive({"focus": 25, "energy": 25, "creativity": 25, "calm": 25})
        assert "terracotta" in result  # fallback brand palette
