"""Tests for Repurpose Engine feature."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_extract_core_ideas():
    from bot.agents.repurpose_agent import extract_core_ideas_sync

    response = """CORE: Лаванда помогает регулировать нервную систему через обоняние
POINTS: снижает кортизол; улучшает сон; работает через лимбическую систему
TONE: educational
AUDIENCE: женщины 25-45, интересующиеся wellness"""

    with patch("bot.services.claude_client.call_claude", return_value=response):
        result = extract_core_ideas_sync("Лаванда — удивительное масло.", "Лаванда")

    assert "нервную систему" in result["core_message"]
    assert len(result["key_points"]) == 3
    assert result["tone"] == "educational"
    assert "wellness" in result["target_audience"]


def test_extract_core_ideas_fallback():
    from bot.agents.repurpose_agent import extract_core_ideas_sync

    with patch("bot.services.claude_client.call_claude", return_value="Непарсимый ответ"):
        result = extract_core_ideas_sync("Текст поста.", "Тема")

    assert result["core_message"] == "Текст поста."
    assert result["key_points"] == []


def test_valid_formats():
    from bot.agents.repurpose_agent import VALID_FORMATS
    assert "carousel" in VALID_FORMATS
    assert "reels_v2" in VALID_FORMATS
    assert "threads_series" in VALID_FORMATS


def test_repurpose_group_model():
    from db.models import RepurposeGroupModel
    assert RepurposeGroupModel.__tablename__ == "repurpose_groups"
    assert hasattr(RepurposeGroupModel, "group_id")
    assert hasattr(RepurposeGroupModel, "source_draft_id")
    assert hasattr(RepurposeGroupModel, "core_message")
    assert hasattr(RepurposeGroupModel, "target_drafts")
    assert hasattr(RepurposeGroupModel, "status")


# ---------------------------------------------------------------------------
# complete_repurpose_generation — carousel draft must carry mood fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repurpose_carousel_stub_inherits_mood_defaults(setup_test_db):
    """When repurposing into a carousel, the stub draft.payload must contain
    goal_key/emotion (inherited from source or defaults), and the launched
    complete_carousel_generation must receive matching kwargs."""
    from unittest.mock import AsyncMock

    from bot.services.drafts_store import get_draft, save_draft
    from bot.services.team_store import create_team
    from db.models import RepurposeGroupModel
    from db.session import AsyncSessionLocal
    from miniapp.api.generation.repurpose import complete_repurpose_generation

    team = await create_team("Repurpose Mood", creator_telegram_id=12345)

    # Source draft is an instagram post — without explicit emotion, defaults apply.
    source = await save_draft(
        kind="instagram",
        topic="Лаванда вечером",
        source="ai",
        payload={"caption": "Текст исходного поста про лаванду.", "goal_key": "authority"},
        team_id=team.team_id,
        created_by=12345,
    )

    # Group row required by orchestrator
    group_id = "grp-test-1"
    async with AsyncSessionLocal() as session:
        session.add(RepurposeGroupModel(
            group_id=group_id,
            source_draft_id=source.draft_id,
            target_drafts=[],
            status="pending",
            core_message="",
            key_points=[],
            team_id=team.team_id,
        ))
        await session.commit()

    # Stub the LLM call for core extraction
    with patch(
        "bot.agents.repurpose_agent.extract_core_ideas_sync",
        return_value={
            "core_message": "core",
            "key_points": [],
            "tone": "educational",
            "target_audience": "",
        },
    ), patch(
        "miniapp.api.generation.complete_carousel_generation",
        new_callable=AsyncMock,
    ) as mock_carousel:
        await complete_repurpose_generation(
            group_id=group_id,
            source_draft_id=source.draft_id,
            target_formats=["carousel"],
            team_id=team.team_id,
            created_by=12345,
        )

    # Find the new carousel stub
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from db.models import DraftModel
        result = await session.execute(
            select(DraftModel).where(DraftModel.kind == "carousel")
        )
        carousel_drafts = result.scalars().all()

    assert len(carousel_drafts) == 1
    payload = carousel_drafts[0].payload
    # goal_key inherited from source (was "authority"); emotion defaults to "calm"
    assert payload.get("goal_key") == "authority"
    assert payload.get("emotion") == "calm"

    # And complete_carousel_generation was called with matching kwargs
    assert mock_carousel.await_count == 1
    kwargs = mock_carousel.call_args.kwargs
    assert kwargs.get("goal_key") == "authority"
    assert kwargs.get("emotion") == "calm"
