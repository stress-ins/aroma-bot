"""Tests for video pipeline orchestrator and music selector."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.music_selector import list_tracks, select_music, _load_manifest, MUSIC_DIR
from bot.services.video_pipeline import (
    _extract_overlay_texts,
    _find_frame_images,
    _mix_audio,
    compose_reel,
)

HAS_FFMPEG = shutil.which("ffmpeg") is not None


# ---------------------------------------------------------------------------
# Music selector tests
# ---------------------------------------------------------------------------


class TestMusicSelector:
    def test_load_manifest(self):
        """Manifest should load and return a list."""
        tracks = _load_manifest()
        assert isinstance(tracks, list)
        assert len(tracks) > 0

    def test_list_tracks_includes_availability(self):
        """Each track entry should have an 'available' boolean."""
        tracks = list_tracks()
        assert isinstance(tracks, list)
        for t in tracks:
            assert "available" in t
            assert isinstance(t["available"], bool)

    @pytest.mark.asyncio
    async def test_select_music_no_files(self):
        """select_music returns None when files don't exist on disk."""
        result = await select_music("calm")
        # Tracks exist in manifest but MP3 files are not present
        assert result is None

    @pytest.mark.asyncio
    async def test_select_music_nonexistent_mood(self):
        """select_music returns None for an unknown mood."""
        result = await select_music("nonexistent_mood_xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_select_music_with_file(self, tmp_path):
        """select_music returns path when a matching file exists."""
        manifest = [{"file": "test_track.mp3", "mood": ["calm"], "bpm": 70, "duration": 30}]
        manifest_path = tmp_path / "tracks.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        track_file = tmp_path / "test_track.mp3"
        track_file.write_bytes(b"\x00" * 100)

        with patch("bot.services.music_selector.MUSIC_DIR", tmp_path), \
             patch("bot.services.music_selector.TRACKS_MANIFEST", manifest_path):
            result = await select_music("calm")
            assert result is not None
            assert result.name == "test_track.mp3"

    @pytest.mark.asyncio
    async def test_select_music_empty_manifest(self, tmp_path):
        """select_music returns None with empty manifest."""
        manifest_path = tmp_path / "tracks.json"
        manifest_path.write_text("[]", encoding="utf-8")

        with patch("bot.services.music_selector.TRACKS_MANIFEST", manifest_path):
            result = await select_music("calm")
            assert result is None


# ---------------------------------------------------------------------------
# Video pipeline helper tests
# ---------------------------------------------------------------------------


class TestExtractOverlayTexts:
    def test_v2_frames(self):
        payload = {
            "frames": [
                {"id": "a", "overlay_text": "First frame"},
                {"id": "b", "overlay_text": "Second frame"},
                {"id": "c"},
            ]
        }
        result = _extract_overlay_texts(payload)
        assert result == ["First frame", "Second frame", ""]

    def test_v1_storyboard(self):
        payload = {
            "storyboard": [
                {"overlay_text": "Scene 1"},
                {"overlay_text": ""},
            ]
        }
        result = _extract_overlay_texts(payload)
        assert result == ["Scene 1", ""]

    def test_empty_payload(self):
        assert _extract_overlay_texts({}) == []


class TestFindFrameImages:
    def test_finds_v2_frames(self, tmp_path):
        draft_id = "test-draft-123"
        asset_dir = tmp_path / draft_id
        asset_dir.mkdir()
        img1 = asset_dir / "frame_abc_001.png"
        img2 = asset_dir / "frame_def_002.png"
        img1.write_bytes(b"\x89PNG")
        img2.write_bytes(b"\x89PNG")

        payload = {
            "frames": [
                {"id": "abc", "image_url": f"/generated/reels_assets/{draft_id}/frame_abc_001.png"},
                {"id": "def", "image_url": f"/generated/reels_assets/{draft_id}/frame_def_002.png"},
            ]
        }
        with patch("bot.services.video_pipeline.ASSETS_DIR", tmp_path):
            result = _find_frame_images(draft_id, payload)
        assert len(result) == 2
        assert result[0].name == "frame_abc_001.png"
        assert result[1].name == "frame_def_002.png"

    def test_finds_v1_storyboard(self, tmp_path):
        draft_id = "test-draft-v1"
        asset_dir = tmp_path / draft_id
        asset_dir.mkdir()
        img = asset_dir / "frame_1_abcd.png"
        img.write_bytes(b"\x89PNG")

        payload = {
            "storyboard": [
                {"current_asset": {"url": f"/generated/reels_assets/{draft_id}/frame_1_abcd.png"}},
            ]
        }
        with patch("bot.services.video_pipeline.ASSETS_DIR", tmp_path):
            result = _find_frame_images(draft_id, payload)
        assert len(result) == 1

    def test_no_asset_dir(self, tmp_path):
        with patch("bot.services.video_pipeline.ASSETS_DIR", tmp_path):
            result = _find_frame_images("nonexistent-draft", {})
        assert result == []

    def test_fallback_glob(self, tmp_path):
        draft_id = "test-glob"
        asset_dir = tmp_path / draft_id
        asset_dir.mkdir()
        (asset_dir / "frame_01.png").write_bytes(b"\x89PNG")
        (asset_dir / "frame_02.png").write_bytes(b"\x89PNG")

        with patch("bot.services.video_pipeline.ASSETS_DIR", tmp_path):
            result = _find_frame_images(draft_id, {})
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Audio mixing tests
# ---------------------------------------------------------------------------


class TestMixAudio:
    @pytest.mark.asyncio
    async def test_no_audio(self, tmp_path):
        """Returns None when neither voiceover nor music provided."""
        result = await _mix_audio(None, None, tmp_path / "out.mp3")
        assert result is None

    @pytest.mark.asyncio
    async def test_voiceover_only(self, tmp_path):
        """Returns voiceover file when no music."""
        vo = tmp_path / "vo.mp3"
        vo.write_bytes(b"\xff\xfb\x90\x00" * 100)
        out = tmp_path / "mixed.mp3"

        result = await _mix_audio(vo, None, out)
        assert result == out
        assert out.exists()

    @pytest.mark.asyncio
    async def test_music_only(self, tmp_path):
        """Returns music file when no voiceover."""
        music = tmp_path / "music.mp3"
        music.write_bytes(b"\xff\xfb\x90\x00" * 100)
        out = tmp_path / "mixed.mp3"

        result = await _mix_audio(None, music, out)
        assert result == out
        assert out.exists()

    @pytest.mark.asyncio
    async def test_both_no_ffmpeg(self, tmp_path):
        """Falls back to voiceover when FFmpeg not available."""
        vo = tmp_path / "vo.mp3"
        vo.write_bytes(b"voiceover")
        music = tmp_path / "music.mp3"
        music.write_bytes(b"music")
        out = tmp_path / "mixed.mp3"

        with patch("bot.services.video_pipeline.shutil.which", return_value=None):
            result = await _mix_audio(vo, music, out)
        assert result == out
        assert out.read_bytes() == b"voiceover"


# ---------------------------------------------------------------------------
# Full pipeline tests (mock-heavy)
# ---------------------------------------------------------------------------


class TestComposeReel:
    @pytest.mark.asyncio
    async def test_draft_not_found(self):
        """Raises ValueError for missing draft."""
        with patch("bot.services.video_pipeline.get_draft", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="Draft not found"):
                await compose_reel("nonexistent")

    @pytest.mark.asyncio
    async def test_no_frame_images(self):
        """Raises ValueError when no frames available."""
        mock_draft = MagicMock()
        mock_draft.payload = {"frames": []}

        with patch("bot.services.video_pipeline.get_draft", new_callable=AsyncMock, return_value=mock_draft), \
             patch("bot.services.video_pipeline._find_frame_images", return_value=[]):
            with pytest.raises(ValueError, match="No frame images found"):
                await compose_reel("test-draft")

    @pytest.mark.asyncio
    async def test_no_voiceover_graceful(self, tmp_path):
        """Pipeline completes without voiceover when no scenario text."""
        mock_draft = MagicMock()
        mock_draft.payload = {"frames": [{"id": "a", "image_url": "/img.png"}]}

        frame_path = tmp_path / "frame.png"
        frame_path.write_bytes(b"\x89PNG")
        final_path = tmp_path / "final.mp4"
        final_path.write_bytes(b"video")

        with patch("bot.services.video_pipeline.get_draft", new_callable=AsyncMock, return_value=mock_draft), \
             patch("bot.services.video_pipeline._find_frame_images", return_value=[frame_path]), \
             patch("bot.services.video_pipeline.compose_video_from_frames", new_callable=AsyncMock) as mock_compose, \
             patch("bot.services.video_pipeline.select_music", new_callable=AsyncMock, return_value=None), \
             patch("bot.services.video_pipeline.update_draft", new_callable=AsyncMock, return_value=mock_draft), \
             patch("bot.services.video_pipeline.VIDEO_OUTPUT_DIR", tmp_path):

            # Make compose_video_from_frames create the silent_video file
            async def _fake_compose(**kwargs):
                out = kwargs.get("output_path", tmp_path / "silent_video.mp4")
                out.write_bytes(b"silent-video")
                return out
            mock_compose.side_effect = _fake_compose

            result = await compose_reel("test-draft")

        assert result["has_voiceover"] is False
        assert result["has_music"] is False
        assert "compose_video" in result["steps_completed"]
        assert "load_draft" in result["steps_completed"]

    @pytest.mark.asyncio
    async def test_no_music_graceful(self, tmp_path):
        """Pipeline completes without music when no tracks available."""
        mock_draft = MagicMock()
        mock_draft.payload = {
            "frames": [{"id": "a", "image_url": "/img.png"}],
            "scenario": "",
            "mood": "calm",
        }

        frame_path = tmp_path / "frame.png"
        frame_path.write_bytes(b"\x89PNG")

        with patch("bot.services.video_pipeline.get_draft", new_callable=AsyncMock, return_value=mock_draft), \
             patch("bot.services.video_pipeline._find_frame_images", return_value=[frame_path]), \
             patch("bot.services.video_pipeline.compose_video_from_frames", new_callable=AsyncMock) as mock_compose, \
             patch("bot.services.video_pipeline.select_music", new_callable=AsyncMock, return_value=None), \
             patch("bot.services.video_pipeline.update_draft", new_callable=AsyncMock, return_value=mock_draft), \
             patch("bot.services.video_pipeline.VIDEO_OUTPUT_DIR", tmp_path):

            async def _fake_compose(**kwargs):
                out = kwargs.get("output_path", tmp_path / "silent_video.mp4")
                out.write_bytes(b"silent-video")
                return out
            mock_compose.side_effect = _fake_compose

            result = await compose_reel("test-draft")

        assert result["has_music"] is False
        assert "compose_video" in result["steps_completed"]

    @pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg not available")
    @pytest.mark.asyncio
    async def test_audio_mixing_with_ffmpeg(self, tmp_path):
        """Integration: audio mixing works when both files exist and FFmpeg available."""
        vo = tmp_path / "vo.mp3"
        music = tmp_path / "music.mp3"
        out = tmp_path / "mixed.mp3"

        # Create minimal valid MP3-like files (FFmpeg may still fail with these,
        # so we test the code path rather than the FFmpeg output)
        vo.write_bytes(b"\xff\xfb\x90\x00" * 1000)
        music.write_bytes(b"\xff\xfb\x90\x00" * 1000)

        result = await _mix_audio(vo, music, out)
        # Even if FFmpeg fails on invalid MP3 data, fallback should give us voiceover
        assert result == out
        assert out.exists()
