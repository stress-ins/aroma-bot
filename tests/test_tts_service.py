"""Tests for bot.services.tts_service."""

from __future__ import annotations

import pytest

from bot.services.tts_service import extract_voiceover_segments


# ---------------------------------------------------------------------------
# extract_voiceover_segments — pure function, no network
# ---------------------------------------------------------------------------


class TestExtractVoiceoverSegments:
    def test_zakadrovy_golos_single(self):
        scenario = (
            "Кадр 1: Визуал лавандового поля\n"
            "Закадровый голос: Лаванда — королева ароматерапии.\n"
            "Длительность: 5 секунд\n"
        )
        result = extract_voiceover_segments(scenario)
        assert len(result) == 1
        assert result[0]["text"] == "Лаванда — королева ароматерапии."
        assert result[0]["duration_hint"] is None

    def test_golos_za_kadrom(self):
        scenario = "Голос за кадром: «Эфирные масла помогают снять стресс»\n"
        result = extract_voiceover_segments(scenario)
        assert len(result) == 1
        assert result[0]["text"] == "Эфирные масла помогают снять стресс"

    def test_multiple_voiceover_lines(self):
        scenario = (
            "Закадровый голос: Первая фраза\n"
            "Визуал: лаванда крупным планом\n"
            "Закадровый голос: Вторая фраза\n"
            "Закадровый голос: Третья фраза\n"
        )
        result = extract_voiceover_segments(scenario)
        assert len(result) == 3
        assert result[0]["text"] == "Первая фраза"
        assert result[1]["text"] == "Вторая фраза"
        assert result[2]["text"] == "Третья фраза"

    def test_frame_based_scenario(self):
        scenario = (
            "Кадр 1: Заголовок на тёмном фоне\n"
            "  Текст: Добро пожаловать в мир ароматов\n"
            "Кадр 2: Флакон масла\n"
            "  Текст: Каждое масло — уникальный набор свойств\n"
        )
        result = extract_voiceover_segments(scenario)
        assert len(result) == 2
        assert "Добро пожаловать" in result[0]["text"]
        assert "уникальный набор" in result[1]["text"]

    def test_empty_scenario(self):
        assert extract_voiceover_segments("") == []

    def test_no_voiceover_markers(self):
        scenario = "Просто какой-то текст без маркеров голоса.\nЕщё строка.\n"
        assert extract_voiceover_segments(scenario) == []

    def test_quoted_voiceover(self):
        scenario = 'Закадровый голос: "Масло чайного дерева — антисептик"\n'
        result = extract_voiceover_segments(scenario)
        assert len(result) == 1
        assert "Масло чайного дерева" in result[0]["text"]


# ---------------------------------------------------------------------------
# generate_single_audio — network call, skip if edge-tts unavailable
# ---------------------------------------------------------------------------

edge_tts_available = True
try:
    import edge_tts  # noqa: F401
except ImportError:
    edge_tts_available = False


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.skipif(not edge_tts_available, reason="edge-tts not installed")
async def test_generate_single_audio(tmp_path):
    from bot.services.tts_service import generate_single_audio

    out = tmp_path / "test_output.mp3"
    result = await generate_single_audio("Привет, мир!", output_path=out)
    assert result == out
    assert result.exists()
    assert result.stat().st_size > 0


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.skipif(not edge_tts_available, reason="edge-tts not installed")
async def test_generate_voiceover_single_segment(tmp_path):
    from bot.services.tts_service import generate_voiceover

    out = tmp_path / "voiceover.mp3"
    result = await generate_voiceover(
        [{"text": "Лаванда успокаивает нервную систему.", "duration_hint": None}],
        output_path=out,
    )
    assert result.exists()
    assert result.stat().st_size > 0


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.skipif(not edge_tts_available, reason="edge-tts not installed")
async def test_generate_voiceover_multi_segment(tmp_path):
    from bot.services.tts_service import generate_voiceover

    out = tmp_path / "multi.mp3"
    segments = [
        {"text": "Первый сегмент.", "duration_hint": None},
        {"text": "Второй сегмент.", "duration_hint": None},
    ]
    result = await generate_voiceover(segments, output_path=out)
    assert result.exists()
    assert result.stat().st_size > 0


# ---------------------------------------------------------------------------
# list_available_voices
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.skipif(not edge_tts_available, reason="edge-tts not installed")
async def test_list_available_voices():
    from bot.services.tts_service import list_available_voices

    voices = await list_available_voices("ru")
    assert isinstance(voices, list)
    assert len(voices) > 0
    # Check structure
    first = voices[0]
    assert "short_name" in first
    assert "gender" in first
    assert "ru" in first["locale"].lower()
