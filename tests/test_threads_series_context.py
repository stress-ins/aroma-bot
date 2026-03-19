"""Tests for threads series trend+handbook context injection."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_build_threads_extra_context_with_trends():
    from miniapp.api.generation.content import _build_threads_extra_context

    mock_posts = [
        {"text": "Trending post about lavender and sleep", "like_count": 10},
        {"text": "Another trend about oils", "like_count": 5},
    ]
    with patch(
        "bot.services.social_trends_store.get_top_posts",
        new_callable=AsyncMock,
        return_value=mock_posts,
    ):
        with patch(
            "bot.services.miniapp_references.list_reference_cards",
            new_callable=AsyncMock,
            return_value=[],
        ):
            text, meta = await _build_threads_extra_context("team1", "утренний ритуал")
    assert "Trending" in text
    assert meta.get("trend_source") is True


@pytest.mark.asyncio
async def test_build_threads_extra_context_with_handbook():
    from miniapp.api.generation.content import _build_threads_extra_context

    mock_cards = [
        {"name_ru": "Лаванда", "name": "Lavender", "description_short": "Успокаивающее масло"},
    ]
    with patch(
        "bot.services.social_trends_store.get_top_posts",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch(
            "bot.services.miniapp_references.list_reference_cards",
            new_callable=AsyncMock,
            return_value=mock_cards,
        ):
            text, meta = await _build_threads_extra_context("team1", "лаванда вечерний")
    assert "Лаванда" in text
    assert meta.get("handbook_source") is True


@pytest.mark.asyncio
async def test_build_threads_extra_context_empty():
    from miniapp.api.generation.content import _build_threads_extra_context

    with patch(
        "bot.services.social_trends_store.get_top_posts",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch(
            "bot.services.miniapp_references.list_reference_cards",
            new_callable=AsyncMock,
            return_value=[],
        ):
            text, meta = await _build_threads_extra_context("team1", "тема")
    assert text == ""
    assert meta == {}


@pytest.mark.asyncio
async def test_build_threads_extra_context_no_team():
    from miniapp.api.generation.content import _build_threads_extra_context

    with patch(
        "bot.services.miniapp_references.list_reference_cards",
        new_callable=AsyncMock,
        return_value=[],
    ):
        text, meta = await _build_threads_extra_context(None, "утренний ритуал")
    assert "trend_source" not in meta
