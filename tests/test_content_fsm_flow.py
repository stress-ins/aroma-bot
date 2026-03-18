"""End-to-end FSM flow tests for the /content command handler.

Tests the full state machine: /content → goal → format → source → topics → pick → draft → approve.
Each handler is called directly with mock Update/Context objects.
Claude API calls are monkeypatched.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.helpers import make_callback_query, make_context, make_update

from bot.agents.content import ContentDraft


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def user_data():
    """Shared user_data dict for a single flow session."""
    return {}


@pytest.fixture
def ctx(user_data):
    return make_context(user_data=user_data)


# ---------------------------------------------------------------------------
# Step 1: /content → shows goal selector
# ---------------------------------------------------------------------------

class TestContentFSMFlow:

    async def test_cmd_content_shows_goal_selector(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        update = make_update(text="/content")

        from bot.handlers.content import cmd_content
        await cmd_content(update, ctx)

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "Выбери цель" in call_args[0][0]
        # Verify keyboard exists
        kb = call_args[1]["reply_markup"]
        assert kb is not None
        # Verify all 4 goal buttons exist
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(all_buttons) == 4
        goal_datas = {btn.callback_data for btn in all_buttons}
        assert "ct:goal:sales" in goal_datas
        assert "ct:goal:trust" in goal_datas

    async def test_cmd_content_requires_api_key(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "")
        update = make_update(text="/content")

        from bot.handlers.content import cmd_content
        await cmd_content(update, ctx)

        update.message.reply_text.assert_called_once()
        assert "ANTHROPIC_API_KEY" in update.message.reply_text.call_args[0][0]

    # ---------------------------------------------------------------------------
    # Step 2: goal callback → shows format selector
    # ---------------------------------------------------------------------------

    async def test_goal_callback_shows_format_selector(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        update = make_callback_query(data="ct:goal:trust")

        from bot.handlers.content import cb_content
        await cb_content(update, ctx)

        update.callback_query.answer.assert_called_once()
        edit_call = update.callback_query.message.edit_text
        edit_call.assert_called_once()
        assert "Доверие" in edit_call.call_args[0][0]
        assert "формат" in edit_call.call_args[0][0].lower()
        assert ctx.user_data["content_goal"] == "trust"

        # Verify format keyboard
        kb = edit_call.call_args[1]["reply_markup"]
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        format_datas = {btn.callback_data for btn in all_buttons}
        assert "ct:format:threads" in format_datas

    # ---------------------------------------------------------------------------
    # Step 3: format callback → shows source selector
    # ---------------------------------------------------------------------------

    async def test_format_callback_shows_source_selector(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        ctx.user_data["content_goal"] = "trust"
        update = make_callback_query(data="ct:format:threads")

        from bot.handlers.content import cb_content
        await cb_content(update, ctx)

        edit_call = update.callback_query.message.edit_text
        edit_call.assert_called_once()
        text = edit_call.call_args[0][0]
        assert "Доверие" in text
        assert "Threads" in text
        assert ctx.user_data["content_format"] == "threads"

        # Verify source keyboard
        kb = edit_call.call_args[1]["reply_markup"]
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        source_datas = {btn.callback_data for btn in all_buttons}
        assert "ct:source:trends" in source_datas
        assert "ct:source:prompt" in source_datas

    async def test_format_carousel_redirects(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        ctx.user_data["content_goal"] = "sales"
        update = make_callback_query(data="ct:format:carousel")

        from bot.handlers.content import cb_content
        await cb_content(update, ctx)

        text = update.callback_query.message.edit_text.call_args[0][0]
        assert "/carousel" in text

    async def test_format_without_goal_errors(self, monkeypatch, ctx):
        """Format callback without prior goal should show error."""
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        update = make_callback_query(data="ct:format:threads")

        from bot.handlers.content import cb_content
        await cb_content(update, ctx)

        reply_call = update.callback_query.message.reply_text
        reply_call.assert_called_once()
        assert "цель" in reply_call.call_args[0][0].lower()

    # ---------------------------------------------------------------------------
    # Step 4: source=prompt → asks for custom text
    # ---------------------------------------------------------------------------

    async def test_source_prompt_asks_for_text(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        ctx.user_data["content_goal"] = "engagement"
        ctx.user_data["content_format"] = "threads"
        update = make_callback_query(data="ct:source:prompt")

        from bot.handlers.content import cb_content
        await cb_content(update, ctx)

        text = update.callback_query.message.edit_text.call_args[0][0]
        assert "направление" in text.lower() or "сообщением" in text.lower()
        assert ctx.user_data["content_awaiting_prompt"] is True

    # ---------------------------------------------------------------------------
    # Step 5: source=trends → generates topics via Claude
    # ---------------------------------------------------------------------------

    async def test_source_trends_generates_topics(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        ctx.user_data["content_goal"] = "trust"
        ctx.user_data["content_format"] = "threads"

        fake_topics = [
            "Как лаванда помогает при бессоннице",
            "Вечерний ритуал для нервной системы",
            "Три масла для снятия стресса",
        ]

        update = make_callback_query(data="ct:source:trends")

        # Mock the cache and topic generation
        from bot.handlers import content as content_mod

        monkeypatch.setattr(content_mod, "generate_topic_options", AsyncMock(return_value=fake_topics))

        # Mock cache
        mock_cache = MagicMock()
        mock_cache.get.return_value = [MagicMock()]  # non-empty results
        monkeypatch.setattr("cache.store.cache", mock_cache)

        await content_mod.cb_content(update, ctx)

        # Should show topics with numbered list
        edit_call = update.callback_query.message.edit_text
        assert edit_call.call_count == 2  # first "Собираю тренды...", then topics
        final_text = edit_call.call_args_list[-1][0][0]
        assert "лаванда" in final_text.lower() or "1." in final_text
        assert ctx.user_data["content_topics"] == fake_topics

    # ---------------------------------------------------------------------------
    # Step 6: pick topic → generates draft via 3-agent chain
    # ---------------------------------------------------------------------------

    async def test_pick_topic_generates_draft(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        ctx.user_data["content_goal"] = "trust"
        ctx.user_data["content_format"] = "threads"
        ctx.user_data["content_topics"] = [
            "Как лаванда помогает при бессоннице",
            "Вечерний ритуал для нервной системы",
        ]

        fake_draft = ContentDraft(
            angle="Через телесные ощущения",
            hook="Бессонница — не приговор",
            caption="Лаванда — одно из самых изученных масел...",
            cta="Напиши, если хочешь попробовать.",
            hashtags="#ароматерапия #лаванда",
            visual_prompt="lavender field, soft light",
        )

        update = make_callback_query(data="ct:pick:0")
        from bot.handlers import content as content_mod

        monkeypatch.setattr(content_mod, "generate_strategist_step", AsyncMock(return_value=("angle", "hook")))
        monkeypatch.setattr(content_mod, "generate_writer_step", AsyncMock(return_value=fake_draft))
        monkeypatch.setattr(content_mod, "save_draft", MagicMock(return_value=MagicMock(draft_id="d001")))
        monkeypatch.setattr(content_mod, "threads_api_enabled", lambda: False)

        await content_mod.cb_content(update, ctx)

        assert ctx.user_data["content_last_topic"] == "Как лаванда помогает при бессоннице"
        assert ctx.user_data["content_last_draft_id"] == "d001"
        assert "content_review_draft" in ctx.user_data

    # ---------------------------------------------------------------------------
    # Step 7: approve → saves draft as approved
    # ---------------------------------------------------------------------------

    async def test_approve_saves_draft(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        ctx.user_data["content_review_draft"] = {
            "goal_key": "trust",
            "caption": "Лаванда — одно из самых изученных масел...",
        }
        ctx.user_data["content_last_draft_id"] = "d001"

        update = make_callback_query(data="ct:approve")
        from bot.handlers import content as content_mod

        mock_updated = MagicMock()
        mock_updated.draft_id = "d001"
        monkeypatch.setattr(content_mod, "update_draft", MagicMock(return_value=mock_updated))

        await content_mod.cb_content(update, ctx)

        content_mod.update_draft.assert_called_once_with("d001", status="approved", payload=ctx.user_data["content_review_draft"])
        reply_text = update.callback_query.message.reply_text.call_args[0][0]
        assert "согласован" in reply_text.lower() or "d001" in reply_text

    # ---------------------------------------------------------------------------
    # Step 8: regen → regenerates same topic
    # ---------------------------------------------------------------------------

    async def test_regen_regenerates_same_topic(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        ctx.user_data["content_last_topic"] = "Лаванда"
        ctx.user_data["content_last_goal"] = "trust"
        ctx.user_data["content_last_format"] = "threads"

        fake_draft = ContentDraft(
            angle="Новый угол",
            hook="Новый хук",
            caption="Новый текст...",
            cta="CTA",
        )

        update = make_callback_query(data="ct:regen")
        from bot.handlers import content as content_mod

        monkeypatch.setattr(content_mod, "generate_strategist_step", AsyncMock(return_value=("angle", "hook")))
        monkeypatch.setattr(content_mod, "generate_writer_step", AsyncMock(return_value=fake_draft))
        monkeypatch.setattr(content_mod, "save_draft", MagicMock(return_value=MagicMock(draft_id="d002")))
        monkeypatch.setattr(content_mod, "threads_api_enabled", lambda: False)

        await content_mod.cb_content(update, ctx)

        assert ctx.user_data["content_last_draft_id"] == "d002"

    # ---------------------------------------------------------------------------
    # Lost context edge cases
    # ---------------------------------------------------------------------------

    async def test_pick_with_stale_topics_errors(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        ctx.user_data["content_goal"] = "trust"
        ctx.user_data["content_format"] = "threads"
        ctx.user_data["content_topics"] = []  # empty

        update = make_callback_query(data="ct:pick:0")

        from bot.handlers.content import cb_content
        await cb_content(update, ctx)

        reply_call = update.callback_query.message.reply_text
        reply_call.assert_called_once()
        assert "устарели" in reply_call.call_args[0][0].lower() or "заново" in reply_call.call_args[0][0].lower()

    async def test_approve_without_draft_errors(self, monkeypatch, ctx):
        monkeypatch.setattr("config.settings.anthropic_api_key", "test-key")
        update = make_callback_query(data="ct:approve")

        from bot.handlers.content import cb_content
        await cb_content(update, ctx)

        reply_call = update.callback_query.message.reply_text
        assert "не найден" in reply_call.call_args[0][0].lower()
