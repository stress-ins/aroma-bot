"""Tests for bot/services/humanizer.py"""
import pytest
from bot.services.humanizer import clean_text, detect_ai_markers, humanize


# ── clean_text: punctuation rules ────────────────────────────────────────────

def test_em_dash_between_words_becomes_comma():
    assert clean_text("тело—сигнал") == "тело, сигнал"


def test_em_dash_with_spaces_becomes_comma():
    assert clean_text("расслабься — почувствуй") == "расслабься, почувствуй"


def test_leading_em_dash_removed():
    result = clean_text("— Начало строки")
    assert not result.startswith("—")


def test_bold_markdown_stripped():
    assert clean_text("**важная мысль**") == "важная мысль"


def test_heading_markdown_stripped():
    result = clean_text("## Заголовок")
    assert result == "Заголовок"


def test_inline_code_stripped():
    assert clean_text("`humanize()`") == "humanize()"


def test_multiple_spaces_collapsed():
    assert clean_text("слово   пробел") == "слово пробел"


def test_multiple_exclamations_collapsed():
    assert clean_text("отлично!!!") == "отлично!"


def test_multiple_questions_collapsed():
    assert clean_text("правда???") == "правда?"


def test_en_dash_with_spaces_becomes_comma():
    assert clean_text("утро – вечер") == "утро, вечер"


def test_en_dash_inside_word_becomes_hyphen():
    assert clean_text("роза–жасмин") == "роза-жасмин"


# ── detect_ai_markers ────────────────────────────────────────────────────────

def test_detect_known_marker():
    markers = detect_ai_markers("Важно отметить, что практика работает.")
    assert any("важно отметить" in m for m in markers)


def test_detect_no_markers_in_clean_text():
    markers = detect_ai_markers("Ложись на пол и закрой глаза на три минуты.")
    assert markers == []


# ── humanize ────────────────────────────────────────────────────────────────

def test_humanize_removes_dashes_and_bold():
    raw = "**Сигнал** — это тело—говорит тебе остановиться."
    result = humanize(raw)
    assert "—" not in result
    assert "**" not in result


def test_humanize_returns_stripped_string():
    result = humanize("  текст  ")
    assert result == result.strip()


def test_humanize_platform_arg_accepted():
    # Should not raise, platform is optional context for logging only
    result = humanize("простой текст", platform="instagram")
    assert result == "простой текст"
