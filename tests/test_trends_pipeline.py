"""Tests for the unified trends pipeline: collect -> enrich -> generate cards."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_pipeline_full_chain(setup_test_db):
    """Pipeline calls collect, enrich, then generate_and_save_cards when enriched > 0."""
    mock_collect = AsyncMock()
    mock_enrich = AsyncMock(return_value=3)
    mock_generate = AsyncMock(return_value=[{"card_id": "a"}, {"card_id": "b"}])

    with (
        patch("bot.services.scheduler._collect_social_trends", mock_collect),
        patch("bot.services.scheduler._PIPELINE_ENRICH_DELAY", 0),
        patch("analytics.signal_enricher.enrich_signals", mock_enrich),
        patch("bot.agents.trend_card_generator.generate_and_save_cards", mock_generate),
    ):
        from bot.services.scheduler import _run_trends_pipeline
        await _run_trends_pipeline()

    mock_collect.assert_awaited_once()
    mock_enrich.assert_awaited_once()
    mock_generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_skips_cards_when_no_enrichment(setup_test_db):
    """When enrich returns 0, card generation is skipped."""
    mock_collect = AsyncMock()
    mock_enrich = AsyncMock(return_value=0)
    mock_generate = AsyncMock(return_value=[])

    with (
        patch("bot.services.scheduler._collect_social_trends", mock_collect),
        patch("bot.services.scheduler._PIPELINE_ENRICH_DELAY", 0),
        patch("analytics.signal_enricher.enrich_signals", mock_enrich),
        patch("bot.agents.trend_card_generator.generate_and_save_cards", mock_generate),
    ):
        from bot.services.scheduler import _run_trends_pipeline
        await _run_trends_pipeline()

    mock_collect.assert_awaited_once()
    mock_enrich.assert_awaited_once()
    mock_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_continues_after_collect_failure(setup_test_db):
    """If collect fails, enrichment still runs."""
    mock_collect = AsyncMock(side_effect=RuntimeError("API down"))
    mock_enrich = AsyncMock(return_value=2)
    mock_generate = AsyncMock(return_value=[{"card_id": "x"}])

    with (
        patch("bot.services.scheduler._collect_social_trends", mock_collect),
        patch("bot.services.scheduler._PIPELINE_ENRICH_DELAY", 0),
        patch("analytics.signal_enricher.enrich_signals", mock_enrich),
        patch("bot.agents.trend_card_generator.generate_and_save_cards", mock_generate),
    ):
        from bot.services.scheduler import _run_trends_pipeline
        await _run_trends_pipeline()

    mock_collect.assert_awaited_once()
    mock_enrich.assert_awaited_once()
    mock_generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_continues_after_enrich_failure(setup_test_db):
    """If enrichment fails, pipeline finishes without crashing (cards skipped)."""
    mock_collect = AsyncMock()
    mock_enrich = AsyncMock(side_effect=RuntimeError("DB error"))
    mock_generate = AsyncMock(return_value=[])

    with (
        patch("bot.services.scheduler._collect_social_trends", mock_collect),
        patch("bot.services.scheduler._PIPELINE_ENRICH_DELAY", 0),
        patch("analytics.signal_enricher.enrich_signals", mock_enrich),
        patch("bot.agents.trend_card_generator.generate_and_save_cards", mock_generate),
    ):
        from bot.services.scheduler import _run_trends_pipeline
        await _run_trends_pipeline()

    mock_collect.assert_awaited_once()
    mock_enrich.assert_awaited_once()
    # enriched stays 0 on failure, so cards not generated
    mock_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_continues_after_cards_failure(setup_test_db):
    """If card generation fails, pipeline still finishes without raising."""
    mock_collect = AsyncMock()
    mock_enrich = AsyncMock(return_value=5)
    mock_generate = AsyncMock(side_effect=RuntimeError("Claude timeout"))

    with (
        patch("bot.services.scheduler._collect_social_trends", mock_collect),
        patch("bot.services.scheduler._PIPELINE_ENRICH_DELAY", 0),
        patch("analytics.signal_enricher.enrich_signals", mock_enrich),
        patch("bot.agents.trend_card_generator.generate_and_save_cards", mock_generate),
    ):
        from bot.services.scheduler import _run_trends_pipeline
        await _run_trends_pipeline()

    # All three stages were attempted
    mock_collect.assert_awaited_once()
    mock_enrich.assert_awaited_once()
    mock_generate.assert_awaited_once()
