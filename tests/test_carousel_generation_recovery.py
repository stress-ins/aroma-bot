"""Recovery behavior for interrupted carousel generation."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _draft(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        draft_id="carousel-1",
        kind="carousel",
        topic="Restful sleep",
        payload=payload,
    )


@pytest.mark.parametrize("slide", [" ", {"heading": None, "body": None}, {"text": 0}])
def test_empty_slide_fields_require_text_recovery(slide):
    from miniapp.api.generation.carousel import has_complete_carousel_text, needs_carousel_text_recovery

    payload = {"slides": [slide], "img_prompts": ["image prompt"]}
    assert needs_carousel_text_recovery(payload)
    assert not has_complete_carousel_text(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("asset_result, expected_pending, expected_stage", [
    ("awaiting_callback", True, "awaiting_callback"),
    ("error", False, "error"),
])
async def test_complete_generation_keeps_asset_outcome(
    asset_result, expected_pending, expected_stage,
):
    """A callback or asset failure must not be overwritten by a done state."""
    draft = _draft({"layout_style": "overlay"})
    module = "miniapp.api.generation.carousel"
    with (
        patch(f"{module}.load_forbidden_phrases", return_value=[]),
        patch(f"{module}._generate_carousel_sync", return_value=(["Slide text"], ["image prompt"], "", "")),
        patch(f"{module}.get_draft", new_callable=AsyncMock, return_value=draft),
        patch(f"{module}.update_draft", new_callable=AsyncMock),
        patch(f"{module}.populate_carousel_slide_assets", new_callable=AsyncMock, return_value=asset_result),
        patch(f"{module}.set_generation_state", new_callable=AsyncMock) as set_state,
    ):
        from miniapp.api.generation.carousel import complete_carousel_generation

        await complete_carousel_generation("carousel-1", "Restful sleep")

    assert set_state.await_args.kwargs["pending"] is expected_pending
    assert set_state.await_args.kwargs["stage"] == expected_stage


@pytest.mark.asyncio
async def test_regenerate_all_rebuilds_empty_text_with_original_generation_options():
    """Recovery from an image-provider failure rebuilds text before images."""
    payload = {
        "slides": [],
        "img_prompts": [],
        "layout_style": "editorial",
        "goal_key": "sales",
        "emotion": "energetic",
        "blend_context": {"title": "Evening blend"},
    }
    module = "miniapp.api.generation.carousel"
    with (
        patch(f"{module}.get_draft", new_callable=AsyncMock, return_value=_draft(payload)),
        patch(f"{module}.complete_carousel_generation", new_callable=AsyncMock) as regenerate,
    ):
        from miniapp.api.generation.carousel import complete_carousel_regenerate_all

        await complete_carousel_regenerate_all("carousel-1")

    regenerate.assert_awaited_once_with(
        "carousel-1", "Restful sleep", {"title": "Evening blend"}, "editorial",
        goal_key="sales", emotion="energetic",
    )


@pytest.mark.asyncio
async def test_regenerate_all_reports_error_when_no_asset_is_replaced():
    """A swallowed provider failure must not make an image-only retry look done."""
    valid = _draft({"slides": ["Slide text"], "img_prompts": ["image prompt"]})
    module = "miniapp.api.generation.carousel"
    with (
        patch(f"{module}.get_draft", new_callable=AsyncMock, return_value=valid),
        patch(f"{module}.regenerate_all_carousel_slide_assets", new_callable=AsyncMock, return_value=valid.payload),
        patch(f"{module}.set_generation_state", new_callable=AsyncMock) as set_state,
    ):
        from miniapp.api.generation.carousel import complete_carousel_regenerate_all

        await complete_carousel_regenerate_all("carousel-1")

    assert set_state.await_args.kwargs["stage"] == "error"
    assert set_state.await_args.kwargs["pending"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("stage, images, pending", [
    ("awaiting_callback", [], True),
    ("error", [], False),
    ("error", [{"pending_callback": True, "kie_task_id": "task-1"}], True),
])
async def test_regenerate_all_preserves_service_outcome(stage, images, pending):
    payload = {"slides": ["Slide text"], "img_prompts": ["image prompt"]}
    module = "miniapp.api.generation.carousel"
    with (
        patch(f"{module}.get_draft", new_callable=AsyncMock, return_value=_draft(payload)),
        patch(f"{module}.regenerate_all_carousel_slide_assets", new_callable=AsyncMock,
              return_value={**payload, "generation_stage": stage, "slide_images": images}),
        patch(f"{module}.set_generation_state", new_callable=AsyncMock) as set_state,
    ):
        from miniapp.api.generation.carousel import complete_carousel_regenerate_all

        await complete_carousel_regenerate_all("carousel-1")

    assert set_state.await_args.kwargs["stage"] == stage
    assert set_state.await_args.kwargs["pending"] is pending
