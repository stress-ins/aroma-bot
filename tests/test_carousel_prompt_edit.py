"""Tests for carousel slide prompt editing (store + API)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Store-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_carousel_slide_prompt():
    """Editing img_prompts[i] persists and does not touch other fields."""
    from bot.services.carousel_assets import update_carousel_slide_prompt
    from bot.services.drafts_store import get_draft, save_draft
    from bot.services.team_store import create_team

    team = await create_team("Store Team", creator_telegram_id=1)
    draft = await save_draft(
        kind="carousel",
        topic="test",
        source="ai",
        payload={
            "slides": ["s1", "s2"],
            "img_prompts": ["original prompt 0", "original prompt 1"],
            "img_prompt_notes": ["", ""],
        },
        team_id=team.team_id,
        created_by=1,
    )
    result = await update_carousel_slide_prompt(draft.draft_id, 0, "edited prompt 0")
    assert result is not None
    assert result["img_prompts"][0] == "edited prompt 0"
    assert result["img_prompts"][1] == "original prompt 1"
    assert result["img_prompt_notes"] == ["", ""]

    refreshed = await get_draft(draft.draft_id)
    assert refreshed.payload["img_prompts"][0] == "edited prompt 0"


@pytest.mark.asyncio
async def test_update_carousel_slide_prompt_out_of_range():
    """Out-of-range slide index returns None."""
    from bot.services.carousel_assets import update_carousel_slide_prompt
    from bot.services.drafts_store import save_draft
    from bot.services.team_store import create_team

    team = await create_team("OOR Store Team", creator_telegram_id=1)
    draft = await save_draft(
        kind="carousel",
        topic="test",
        source="ai",
        payload={"slides": ["s1"], "img_prompts": ["p1"]},
        team_id=team.team_id,
        created_by=1,
    )
    result = await update_carousel_slide_prompt(draft.draft_id, 5, "bad")
    assert result is None


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setenv("AROMA_BYPASS_AUTH", "1")
    monkeypatch.setenv("AROMA_ENV", "test")


HEADERS = {
    "X-Telegram-Init-Data": "user=%7B%22id%22%3A12345%7D&auth_date=9999999999&hash=abc",
}


def _client():
    from miniapp_server import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.asyncio
async def test_api_update_slide_prompt():
    """POST /api/carousel/{id}/slides/{i}/prompt updates img_prompts."""
    from bot.services.drafts_store import save_draft
    from bot.services.team_store import create_team

    team = await create_team("Prompt Team", creator_telegram_id=12345)
    draft = await save_draft(
        kind="carousel",
        topic="Prompt test",
        source="ai",
        payload={
            "slides": [{"heading": "S1"}, {"heading": "S2"}],
            "img_prompts": ["old prompt 0", "old prompt 1"],
        },
        team_id=team.team_id,
        created_by=12345,
    )

    client = _client()
    resp = client.post(
        f"/api/carousel/{draft.draft_id}/slides/0/prompt",
        json={"prompt": "new prompt 0"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["payload"]["img_prompts"][0] == "new prompt 0"
    assert data["payload"]["img_prompts"][1] == "old prompt 1"


@pytest.mark.asyncio
async def test_api_update_slide_prompt_not_found():
    """POST with nonexistent draft returns 404."""
    client = _client()
    resp = client.post(
        "/api/carousel/nonexistent/slides/0/prompt",
        json={"prompt": "x"},
        headers=HEADERS,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_update_slide_prompt_out_of_range():
    """POST with out-of-range slide index returns 404."""
    from bot.services.drafts_store import save_draft
    from bot.services.team_store import create_team

    team = await create_team("OOR Team", creator_telegram_id=12345)
    draft = await save_draft(
        kind="carousel",
        topic="OOR test",
        source="ai",
        payload={
            "slides": [{"heading": "S1"}],
            "img_prompts": ["p1"],
        },
        team_id=team.team_id,
        created_by=12345,
    )

    client = _client()
    resp = client.post(
        f"/api/carousel/{draft.draft_id}/slides/5/prompt",
        json={"prompt": "bad"},
        headers=HEADERS,
    )
    assert resp.status_code == 404
