"""Tests for Canva background task worker and partitioned task store."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from bot.services.canva_task_worker import (
    _execute_export,
    _execute_import,
    _status_key,
    live_status,
)

# Shorthand for the module path where names are imported
_W = "bot.services.canva_task_worker"


def test_status_key():
    assert _status_key("draft-1", "canva_export") == "draft-1:canva_export"
    assert _status_key("draft-1", "canva_import") == "draft-1:canva_import"


@pytest.mark.asyncio
async def test_execute_export(tmp_path):
    """Worker export reads PPTX from file and calls export_to_canva."""
    pptx_file = tmp_path / "_canva_export.pptx"
    pptx_file.write_bytes(b"fake-pptx-bytes")

    task = MagicMock()
    task.task_id = "t-1"
    task.draft_id = "d-1"
    task.task_type = "canva_export"
    task.config = {"pptx_path": str(pptx_file), "title": "Test"}

    canva_result = {"design_id": "des-1", "edit_url": "https://canva.com/edit/des-1"}

    with patch(f"{_W}.update_task_progress", new_callable=AsyncMock), \
         patch("bot.services.canva_api.export_to_canva", new_callable=AsyncMock, return_value=canva_result) as mock_export:
        key = _status_key("d-1", "canva_export")
        live_status[key] = {"task_id": "t-1", "task_type": "canva_export", "status": "running", "step": "starting"}

        result = await _execute_export(task)

    assert result == canva_result
    mock_export.assert_called_once_with(b"fake-pptx-bytes", "Test")
    assert not pptx_file.exists()


@pytest.mark.asyncio
async def test_execute_export_missing_file():
    """Worker export fails gracefully when PPTX file is missing."""
    task = MagicMock()
    task.task_id = "t-2"
    task.draft_id = "d-2"
    task.task_type = "canva_export"
    task.config = {"pptx_path": "/nonexistent/file.pptx", "title": "Test"}

    key = _status_key("d-2", "canva_export")
    live_status[key] = {"task_id": "t-2", "task_type": "canva_export", "status": "running", "step": "starting"}

    with patch(f"{_W}.update_task_progress", new_callable=AsyncMock):
        with pytest.raises(FileNotFoundError):
            await _execute_export(task)


@pytest.mark.asyncio
async def test_execute_import():
    """Worker import downloads PPTX, extracts images, updates draft."""
    task = MagicMock()
    task.task_id = "t-3"
    task.draft_id = "d-3"
    task.task_type = "canva_import"
    task.config = {"design_id": "des-abc"}

    mock_draft = MagicMock()
    mock_draft.payload = {"img_prompts": ["p1", "p2"], "slide_images": [None, None], "slide_image_versions": [[], []]}

    fake_version = {"path": "v1.webp", "ts": 123}

    with patch("bot.services.canva_api.export_canva_design", new_callable=AsyncMock, return_value=b"pptx-data"), \
         patch("bot.services.carousel_assets.extract_images_from_pptx", return_value=[b"img1", b"img2"]), \
         patch("bot.services.carousel_assets.save_carousel_slide_asset", return_value=fake_version), \
         patch("bot.services.drafts_store.get_draft", new_callable=AsyncMock, return_value=mock_draft), \
         patch("bot.services.drafts_store.update_draft", new_callable=AsyncMock) as mock_update, \
         patch("bot.services.draft_revisions_store.create_revision", new_callable=AsyncMock), \
         patch(f"{_W}.update_task_progress", new_callable=AsyncMock):

        key = _status_key("d-3", "canva_import")
        live_status[key] = {"task_id": "t-3", "task_type": "canva_import", "status": "running", "step": "starting"}

        result = await _execute_import(task)

    assert result["images_ready"] == 2
    assert result["design_id"] == "des-abc"
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args
    assert call_kwargs.kwargs["status"] == "approved"


@pytest.mark.asyncio
async def test_claim_next_task_partitioned():
    """claim_next_task with task_types only returns matching types."""
    from bot.services.video_task_store import claim_next_task, enqueue_task, complete_task

    canva_task = await enqueue_task("d-part-1", "canva_export", {"pptx_path": "/tmp/x.pptx"})

    # Video worker should NOT claim it
    video_claim = await claim_next_task(task_types=("clean", "compose"))
    assert video_claim is None

    # Canva worker SHOULD claim it
    canva_claim = await claim_next_task(task_types=("canva_export", "canva_import"))
    assert canva_claim is not None
    assert canva_claim.task_id == canva_task.task_id

    await complete_task(canva_task.task_id)


@pytest.mark.asyncio
async def test_recover_interrupted_tasks_partitioned():
    """recover_interrupted_tasks with task_types only resets matching types."""
    from bot.services.video_task_store import enqueue_task, claim_next_task, recover_interrupted_tasks, get_task, complete_task

    video_task = await enqueue_task("d-recov-1", "clean", {"src": "x"})
    canva_task = await enqueue_task("d-recov-2", "canva_export", {"pptx_path": "y"})

    # Claim both
    await claim_next_task()
    await claim_next_task()

    # Recover only canva tasks
    count = await recover_interrupted_tasks(task_types=("canva_export", "canva_import"))
    assert count == 1

    ct = await get_task(canva_task.task_id)
    assert ct.status == "pending"

    vt = await get_task(video_task.task_id)
    assert vt.status == "running"

    # Clean up
    await complete_task(video_task.task_id)
    await complete_task(canva_task.task_id)
