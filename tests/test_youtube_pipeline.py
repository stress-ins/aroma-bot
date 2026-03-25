"""Tests for the YouTube content pipeline.

Covers:
- youtube_script_agent: parsing, topic generation
- broll_director: parsing, extraction
- thumbnail_generator: prompt parsing, payload building
- youtube_metadata_agent: parsing, timecode formatting
- video_composer: FORMAT_LANDSCAPE support
"""
from __future__ import annotations

import pytest

# ── YouTube Script Agent ──────────────────────────────────────────────────

class TestYouTubeScriptParsing:
    """Test parsing of YouTube script responses."""

    def test_parse_talking_head_script(self):
        from bot.agents.youtube_script_agent import _parse_youtube_script

        raw = """\
TITLE: 5 масел для глубокого сна

SECTION: HOOK
TIMECODE: 0:00–0:30
SPEAKER_TEXT: Знаете ли вы, что 40% людей спят плохо?
SCREEN_TEXT: 40% людей
ENERGY: high
[B-ROLL: крупный план подушки с каплями лаванды]

SECTION: INTRO
TIMECODE: 0:30–1:30
SPEAKER_TEXT: Привет! Сегодня я расскажу о 5 маслах для сна.
SCREEN_TEXT: 5 масел для сна
ENERGY: medium
[B-ROLL: общий план спальни]

SECTION: MAIN_1
TIMECODE: 1:30–3:30
LABEL: Лаванда
SPEAKER_TEXT: Первое масло — лаванда. Исследования показывают...
SCREEN_TEXT: Лаванда: -30% кортизол
ENERGY: medium
[B-ROLL: поля лаванды в Провансе]

SECTION: RECAP
TIMECODE: 8:00–8:30
SPEAKER_TEXT: Итак, мы разобрали 5 масел.
SCREEN_TEXT: Резюме
ENERGY: medium
[B-ROLL: все масла на столе]

SECTION: CTA
TIMECODE: 8:30–9:00
SPEAKER_TEXT: Подписывайтесь и ставьте лайк!
SCREEN_TEXT: Подпишись
ENERGY: high
[B-ROLL: лого канала]

MUSIC_MOOD: спокойная, ambient, пианино
"""
        script = _parse_youtube_script(raw, "talking_head")

        assert script.title == "5 масел для глубокого сна"
        assert script.subformat == "talking_head"
        assert script.music_mood == "спокойная, ambient, пианино"
        assert len(script.sections) == 5

        hook = script.sections[0]
        assert hook.section_type == "HOOK"
        assert "40%" in hook.speaker_text
        assert hook.energy == "high"
        assert "лаванды" in hook.broll_cue

        main = script.sections[2]
        assert main.section_type == "MAIN_1"
        assert main.label == "Лаванда"

    def test_parse_podcast_script(self):
        from bot.agents.youtube_script_agent import _parse_youtube_script

        raw = """\
TITLE: Ароматерапия и нервная система

GUEST_NAME: Доктор Иванова
GUEST_EXPERTISE: Нейрофизиология ароматерапии

SECTION: COLD_OPEN
TIMECODE: 0:00–0:30
SPEAKER_TEXT: Запах лаванды активирует парасимпатику за 3 минуты.
SCREEN_TEXT: 3 минуты
ENERGY: high
[B-ROLL: мозг в МРТ]

SECTION: QUESTION_1
TIMECODE: 2:00–5:00
LABEL: Как работает обоняние
HOST_TEXT: Расскажите, как обоняние влияет на нервную систему?
GUEST_TALKING_POINTS:
- Обонятельная луковица связана с лимбической системой
- Запахи минуют кору — прямой доступ к эмоциям
- Лаванда снижает кортизол в исследованиях
FOLLOW_UP: А как быстро это работает?
ENERGY: medium
[B-ROLL: схема мозга]

MUSIC_MOOD: фоновый ambient
"""
        script = _parse_youtube_script(raw, "podcast")

        assert script.guest_name == "Доктор Иванова"
        assert "Нейрофизиология" in script.guest_expertise
        assert len(script.sections) == 2

        q1 = script.sections[1]
        assert q1.section_type == "QUESTION_1"
        assert len(q1.guest_talking_points) == 3
        assert q1.follow_up == "А как быстро это работает?"

    def test_parse_empty_returns_empty_sections(self):
        from bot.agents.youtube_script_agent import _parse_youtube_script
        script = _parse_youtube_script("", "talking_head")
        assert script.sections == []
        assert script.title == ""


class TestYouTubeScriptPayload:
    def test_script_to_payload(self):
        from bot.agents.youtube_script_agent import YouTubeScript, YouTubeSection, script_to_payload

        script = YouTubeScript(
            title="Test Title",
            subformat="listicle",
            sections=[
                YouTubeSection(
                    section_type="HOOK",
                    label="Hook",
                    timecode="0:00–0:30",
                    speaker_text="Hello",
                    screen_text="Hi",
                    energy="high",
                    broll_cue="nature shot",
                ),
            ],
            music_mood="calm",
            duration_target=10,
        )
        payload = script_to_payload(script)

        assert payload["title"] == "Test Title"
        assert payload["subformat"] == "listicle"
        assert len(payload["sections"]) == 1
        assert payload["sections"][0]["broll_cue"] == "nature shot"


class TestTimecodeHelpers:
    def test_fmt_time(self):
        from bot.agents.youtube_script_agent import _fmt_time
        assert _fmt_time(0) == "0:00"
        assert _fmt_time(90) == "1:30"
        assert _fmt_time(605) == "10:05"

    def test_compute_section_timecodes(self):
        from bot.agents.youtube_script_agent import _compute_section_timecodes
        tc = _compute_section_timecodes(10, "talking_head")
        assert "section_end_1" in tc
        assert "total_end" in tc
        assert tc["total_end"] == "10:00"


# ── B-Roll Director ──────────────────────────────────────────────────────

class TestBRollDirector:
    def test_parse_broll_map(self):
        from bot.agents.broll_director import _parse_broll_map

        raw = """\
BROLL_1:
SECTION: HOOK
TIMESTAMP: 0:15
DURATION: 4
DESCRIPTION: крупный план: капли масла на ладони
SOURCE_TYPE: stock_video
SEARCH_KEYWORDS: essential oil, hand, drops, aromatherapy
CAMERA_MOTION: slow_zoom_in
MOOD: calm

BROLL_2:
SECTION: MAIN_1
TIMESTAMP: 2:30
DURATION: 5
DESCRIPTION: поля лаванды на закате
SOURCE_TYPE: stock_photo
SEARCH_KEYWORDS: lavender field, sunset, Provence
CAMERA_MOTION: pan_left
MOOD: warm
"""
        cues = _parse_broll_map(raw)
        assert len(cues) == 2

        assert cues[0].section_name == "HOOK"
        assert cues[0].timestamp == "0:15"
        assert cues[0].duration == 4.0
        assert cues[0].source_type == "stock_video"
        assert len(cues[0].search_keywords) == 4
        assert cues[0].camera_motion == "slow_zoom_in"

        assert cues[1].mood == "warm"

    def test_extract_broll_from_sections(self):
        from bot.agents.broll_director import extract_broll_from_sections

        sections = [
            {"section_type": "HOOK", "timecode": "0:00–0:30", "broll_cue": "лаванда крупным планом"},
            {"section_type": "INTRO", "timecode": "0:30–1:30", "broll_cue": ""},
            {"section_type": "MAIN_1", "timecode": "1:30–3:30", "broll_cue": "диффузор в комнате"},
        ]
        cues = extract_broll_from_sections(sections)
        assert len(cues) == 2
        assert cues[0].section_name == "HOOK"
        assert cues[1].description == "диффузор в комнате"

    def test_broll_map_to_payload(self):
        from bot.agents.broll_director import BRollCue, broll_map_to_payload

        cues = [BRollCue(
            section_name="HOOK",
            timestamp="0:15",
            duration=4.0,
            description="test",
            source_type="stock_photo",
            search_keywords=["oil"],
            camera_motion="static",
            mood="calm",
        )]
        payload = broll_map_to_payload(cues)
        assert len(payload) == 1
        assert payload[0]["image_status"] == "pending"
        assert payload[0]["image_url"] == ""

    def test_duration_clamped(self):
        from bot.agents.broll_director import _parse_broll_map
        raw = "BROLL_1:\nSECTION: X\nDURATION: 100\nDESCRIPTION: test"
        cues = _parse_broll_map(raw)
        assert cues[0].duration == 8.0  # clamped to max

        raw2 = "BROLL_1:\nSECTION: X\nDURATION: 0.5\nDESCRIPTION: test"
        cues2 = _parse_broll_map(raw2)
        assert cues2[0].duration == 2.0  # clamped to min


# ── Thumbnail Generator ──────────────────────────────────────────────────

class TestThumbnailGenerator:
    def test_parse_thumbnail_response(self):
        from bot.services.thumbnail_generator import _parse_thumbnail_response

        raw = """\
PROMPT: Cinematic still of lavender oil bottle on wooden table, warm light, 1280x720
TEXT_OVERLAY: 5 масел для сна
"""
        result = _parse_thumbnail_response(raw)
        assert "lavender" in result["prompt"]
        assert "5 масел" in result["text_overlay"]

    def test_build_thumbnail_payload(self):
        from bot.services.thumbnail_generator import build_thumbnail_payload

        payload = build_thumbnail_payload(
            mode="prompt",
            prompt="test prompt",
            text_overlay="Test",
            result_path="/data/thumbnails/abc123/thumb.jpg",
        )
        assert payload["mode"] == "prompt"
        assert payload["prompt"] == "test prompt"
        assert "abc123" in payload["result_url"]
        assert payload["history"] == []

    def test_build_upload_payload(self):
        from bot.services.thumbnail_generator import build_thumbnail_payload
        payload = build_thumbnail_payload(mode="upload", result_path="/tmp/my.jpg")
        assert payload["mode"] == "upload"
        assert payload["prompt"] == ""


# ── YouTube Metadata Agent ───────────────────────────────────────────────

class TestYouTubeMetadata:
    def test_parse_metadata(self):
        from bot.agents.youtube_metadata_agent import _parse_metadata

        raw = """\
TITLE: 5 эфирных масел для сна | Ароматерапия

DESCRIPTION:
В этом видео разбираем 5 эфирных масел для улучшения сна.

⏱ Таймкоды:
0:00 — Введение
0:32 — Масло #1: Лаванда
3:12 — Масло #2: Ветивер

#ароматерапия #сон #эфирныемасла

TAGS: ароматерапия, эфирные масла, сон, лаванда, ветивер, масла для сна

CATEGORY: 26
"""
        meta = _parse_metadata(raw)
        assert "5 эфирных масел" in meta.title
        assert len(meta.tags) == 6
        assert meta.category_id == 26
        assert len(meta.chapters) == 3
        assert meta.chapters[0]["time"] == 0
        assert meta.chapters[1]["time"] == 32
        assert meta.chapters[2]["time"] == 192  # 3*60 + 12

    def test_fmt_timecode(self):
        from bot.agents.youtube_metadata_agent import _fmt_timecode
        assert _fmt_timecode(0) == "0:00"
        assert _fmt_timecode(62) == "1:02"
        assert _fmt_timecode(3661) == "1:01:01"

    def test_build_timecodes_block(self):
        from bot.agents.youtube_metadata_agent import build_timecodes_block
        sections = [
            {"label": "Intro", "start_seconds": 0},
            {"label": "Main", "start_seconds": 90},
        ]
        block = build_timecodes_block(sections)
        assert "0:00 — Intro" in block
        assert "1:30 — Main" in block

    def test_metadata_to_payload(self):
        from bot.agents.youtube_metadata_agent import YouTubeMetadata, metadata_to_payload
        meta = YouTubeMetadata(
            title="Test",
            description="Desc",
            tags=["a", "b"],
            category_id=26,
            chapters=[{"time": 0, "title": "Intro"}],
        )
        payload = metadata_to_payload(meta)
        assert payload["title"] == "Test"
        assert len(payload["chapters"]) == 1


# ── Video Composer Landscape ─────────────────────────────────────────────

class TestVideoComposerLandscape:
    def test_format_landscape_dimensions(self):
        from bot.services.video_composer import FORMAT_LANDSCAPE, FORMAT_PORTRAIT

        assert FORMAT_LANDSCAPE.width == 1920
        assert FORMAT_LANDSCAPE.height == 1080
        assert FORMAT_PORTRAIT.width == 1080
        assert FORMAT_PORTRAIT.height == 1920

    def test_format_kb_dimensions_even(self):
        from bot.services.video_composer import FORMAT_LANDSCAPE, FORMAT_PORTRAIT

        # All KB dimensions must be even for H.264
        assert FORMAT_LANDSCAPE.kb_width % 2 == 0
        assert FORMAT_LANDSCAPE.kb_height % 2 == 0
        assert FORMAT_PORTRAIT.kb_width % 2 == 0
        assert FORMAT_PORTRAIT.kb_height % 2 == 0

    def test_kb_filter_uses_format(self):
        from bot.services.video_composer import FORMAT_LANDSCAPE, _kb_filter

        filt = _kb_filter(0, 5.0, fmt=FORMAT_LANDSCAPE)
        assert "1920x1080" in filt
        assert "zoompan" in filt

    def test_kb_filter_default_portrait(self):
        from bot.services.video_composer import _kb_filter

        filt = _kb_filter(0, 5.0)
        assert "1080x1920" in filt


# ── YouTube Pipeline helpers ─────────────────────────────────────────────

class TestYouTubePipelineHelpers:
    def test_build_tts_segments(self):
        from bot.services.youtube_pipeline import _build_tts_segments_from_sections

        sections = [
            {"speaker_text": "Привет!", "section_type": "HOOK", "label": "Hook"},
            {"speaker_text": "", "host_text": "Добро пожаловать", "section_type": "INTRO", "label": "Intro"},
            {"speaker_text": "", "section_type": "EMPTY", "label": "Empty"},
        ]
        segments = _build_tts_segments_from_sections(sections)
        assert len(segments) == 2
        assert segments[0]["text"] == "Привет!"
        assert segments[1]["text"] == "Добро пожаловать"


# ── API Models ───────────────────────────────────────────────────────────

class TestAPIModels:
    def test_create_youtube_payload_defaults(self):
        from miniapp.api.models import CreateYouTubePayload
        p = CreateYouTubePayload()
        assert p.subformat == "talking_head"
        assert p.duration_target == 10
        assert p.goal == "trust"

    def test_create_youtube_payload_podcast(self):
        from miniapp.api.models import CreateYouTubePayload
        p = CreateYouTubePayload(
            topic="Ароматерапия",
            subformat="podcast",
            duration_target=30,
            question_count=8,
            guest_description="Доктор Иванова",
        )
        assert p.subformat == "podcast"
        assert p.question_count == 8

    def test_thumbnail_payload(self):
        from miniapp.api.models import YouTubeThumbnailPayload
        p = YouTubeThumbnailPayload(mode="photo_based", revision_note="сделай ярче")
        assert p.mode == "photo_based"
        assert p.revision_note == "сделай ярче"
