"""End-to-end FSM flow tests for the /carousel command handler.

Tests the state machine: /carousel → source → topics → pick topic.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.helpers import make_callback_query, make_context, make_update


class TestCarouselFSMFlow:

    # ---------------------------------------------------------------------------
    # Step 1: /carousel → shows source selector
    # ---------------------------------------------------------------------------

    async def test_cmd_carousel_shows_source_selector(self, monkeypatch):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        update = make_update(text="/carousel")
        ctx = make_context()

        from bot.handlers.carousel import cmd_carousel
        await cmd_carousel(update, ctx)

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "Карусель" in call_args[0][0]
        kb = call_args[1]["reply_markup"]
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        datas = {btn.callback_data for btn in all_buttons}
        assert "ca:source:trends" in datas
        assert "ca:source:custom" in datas

    async def test_cmd_carousel_requires_api_key(self, monkeypatch):
        monkeypatch.setattr("config.settings.anthropic_api_key", "")
        update = make_update(text="/carousel")
        ctx = make_context()

        from bot.handlers.carousel import cmd_carousel
        await cmd_carousel(update, ctx)

        assert "ANTHROPIC_API_KEY" in update.message.reply_text.call_args[0][0]

    async def test_cmd_carousel_clears_state(self, monkeypatch):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        update = make_update(text="/carousel")
        ctx = make_context(user_data={
            "ca_awaiting_images": True,
            "ca_awaiting_topic": True,
        })

        from bot.handlers.carousel import cmd_carousel
        await cmd_carousel(update, ctx)

        assert ctx.user_data["ca_awaiting_images"] is False
        assert ctx.user_data["ca_awaiting_topic"] is False

    # ---------------------------------------------------------------------------
    # Step 2: custom source → awaiting topic input
    # ---------------------------------------------------------------------------

    async def test_source_custom_awaits_topic(self, monkeypatch):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        update = make_callback_query(data="ca:source:custom")
        ctx = make_context()

        from bot.handlers.carousel import cb_carousel
        await cb_carousel(update, ctx)

        update.callback_query.answer.assert_called_once()
        text = update.callback_query.message.edit_text.call_args[0][0]
        assert "тему" in text.lower()
        assert ctx.user_data["ca_awaiting_topic"] is True

    # ---------------------------------------------------------------------------
    # Step 3: trends source → generates and shows topics
    # ---------------------------------------------------------------------------

    async def test_source_trends_generates_topics(self, monkeypatch):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        fake_topics = ["Аромат и стресс", "Утренний ритуал", "Гонг-медитация"]

        from bot.handlers import carousel as carousel_mod

        # Mock cache
        mock_cache = MagicMock()
        mock_cache.get.return_value = [MagicMock()]  # non-empty
        monkeypatch.setattr("cache.store.cache", mock_cache)

        # Mock _claude_topics_carousel to return fake topics
        monkeypatch.setattr(carousel_mod, "_claude_topics_carousel", lambda _: fake_topics)

        update = make_callback_query(data="ca:source:trends")
        ctx = make_context()

        await carousel_mod.cb_carousel(update, ctx)

        # Should have called edit_text multiple times (progress + result)
        edit_calls = update.callback_query.message.edit_text.call_args_list
        assert len(edit_calls) >= 2
        final_text = edit_calls[-1][0][0]
        assert "1." in final_text
        assert ctx.user_data["ca_topics"] == fake_topics

        # Verify keyboard has topic buttons
        kb = edit_calls[-1][1]["reply_markup"]
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        datas = {btn.callback_data for btn in all_buttons}
        assert "ca:g:0" in datas

    # ---------------------------------------------------------------------------
    # Step 4: pick topic with stale data → error
    # ---------------------------------------------------------------------------

    async def test_pick_stale_topic_errors(self, monkeypatch):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        update = make_callback_query(data="ca:g:5")
        ctx = make_context(user_data={"ca_topics": []})

        from bot.handlers.carousel import cb_carousel
        await cb_carousel(update, ctx)

        reply_call = update.callback_query.message.reply_text
        reply_call.assert_called_once()
        assert "устарели" in reply_call.call_args[0][0].lower()

    # ---------------------------------------------------------------------------
    # Keyboard structure validation
    # ---------------------------------------------------------------------------

    def test_source_keyboard_structure(self):
        from bot.handlers.carousel import _source_keyboard
        kb = _source_keyboard()
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(all_buttons) == 2
        for btn in all_buttons:
            assert btn.callback_data
            assert btn.text

    def test_topics_keyboard_structure(self):
        from bot.handlers.carousel import _topics_keyboard
        topics = ["Topic A", "Topic B", "Topic C"]
        kb = _topics_keyboard(topics)
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        # 3 topic buttons + 1 refresh button
        assert len(all_buttons) == 4
        datas = [btn.callback_data for btn in all_buttons]
        assert "ca:g:0" in datas
        assert "ca:g:2" in datas
        assert all(btn.text for btn in all_buttons)
