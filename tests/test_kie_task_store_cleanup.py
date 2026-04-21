"""Tests for kie_task_store.cleanup_expired — expiring pending tasks must
synchronise the corresponding draft slot so the UI stops spinning forever."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


async def _insert_expired_task(task_id: str, *, draft_id: str, content_type: str, slot_key: str, age_minutes: int = 45) -> None:
    """Insert a pending kie_task whose created_at is older than the cleanup cutoff."""
    from db.models import KieTaskModel
    from db.session import AsyncSessionLocal

    old = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    async with AsyncSessionLocal() as s:
        s.add(KieTaskModel(
            task_id=task_id,
            status="pending",
            draft_id=draft_id,
            content_type=content_type,
            slot_key=slot_key,
            prompt="prompt",
            aspect_ratio="4:5",
            model="gpt-image",
            image_url="",
            error_message="",
            created_at=old,
        ))
        await s.commit()


async def _insert_draft(draft_id: str, *, kind: str, payload: dict) -> None:
    from db.models import DraftModel
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        s.add(DraftModel(
            draft_id=draft_id,
            kind=kind,
            topic="topic",
            source="test",
            status="draft",
            feedback="",
            payload=payload,
        ))
        await s.commit()


async def _reload_draft(draft_id: str) -> dict:
    from bot.services.drafts_store import get_draft
    d = await get_draft(draft_id)
    assert d is not None
    return d.payload


async def _reload_task_status(task_id: str) -> str:
    from bot.services.kie_task_store import get_task
    t = await get_task(task_id)
    assert t is not None
    return t.status


class TestCleanupExpiredCarousel:
    async def test_expired_carousel_slot_marked_failed_and_stage_error(self):
        """Single carousel slide whose kie_task expired → slide marked failed, stage='error'."""
        from bot.services.kie_task_store import cleanup_expired

        await _insert_draft(
            "car1",
            kind="carousel",
            payload={
                "slides": ["s1", "s2", "s3"],
                "img_prompts": ["p1", "p2", "p3"],
                "slide_images": [
                    {"url": "/a.png", "filename": "a.png"},
                    {"url": "/b.png", "filename": "b.png"},
                    None,
                ],
                "generation_pending": True,
                "generation_stage": "awaiting_callback",
            },
        )
        await _insert_expired_task("tkn-car1-slot2", draft_id="car1", content_type="carousel_slide", slot_key="2")

        count = await cleanup_expired(max_age_minutes=30)
        assert count == 1

        assert await _reload_task_status("tkn-car1-slot2") == "expired"

        payload = await _reload_draft("car1")
        # Ready slides must not be touched.
        assert payload["slide_images"][0] == {"url": "/a.png", "filename": "a.png"}
        assert payload["slide_images"][1] == {"url": "/b.png", "filename": "b.png"}
        # Failed slot now carries an explicit failure marker.
        failed = payload["slide_images"][2]
        assert isinstance(failed, dict)
        assert failed.get("failed") is True
        assert failed.get("error") == "timeout"
        # Draft-level state reflects the failure.
        assert payload["generation_pending"] is False
        assert payload["generation_stage"] == "error"

    async def test_expired_with_other_pending_keeps_state(self):
        """If another task for the same draft is still pending, we keep
        generation_pending=True and don't overwrite stage."""
        from bot.services.kie_task_store import cleanup_expired

        await _insert_draft(
            "car2",
            kind="carousel",
            payload={
                "slides": ["s1", "s2"],
                "img_prompts": ["p1", "p2"],
                "slide_images": [None, None],
                "generation_pending": True,
                "generation_stage": "awaiting_callback",
            },
        )
        await _insert_expired_task("tkn-car2-old", draft_id="car2", content_type="carousel_slide", slot_key="0", age_minutes=45)
        # fresh pending task, should NOT expire yet
        await _insert_expired_task("tkn-car2-fresh", draft_id="car2", content_type="carousel_slide", slot_key="1", age_minutes=5)

        count = await cleanup_expired(max_age_minutes=30)
        assert count == 1
        assert await _reload_task_status("tkn-car2-fresh") == "pending"

        payload = await _reload_draft("car2")
        assert payload["slide_images"][0]["failed"] is True
        # Second slot still awaits callback — untouched.
        assert payload["slide_images"][1] is None
        # Draft-level state: pending stays True (another task in flight).
        assert payload["generation_pending"] is True

    async def test_no_expired_noop(self):
        from bot.services.kie_task_store import cleanup_expired

        await _insert_draft(
            "car3",
            kind="carousel",
            payload={
                "slides": ["s1"],
                "img_prompts": ["p1"],
                "slide_images": [None],
                "generation_pending": True,
                "generation_stage": "awaiting_callback",
            },
        )
        # fresh pending task — not yet expired
        await _insert_expired_task("tkn-car3", draft_id="car3", content_type="carousel_slide", slot_key="0", age_minutes=5)

        count = await cleanup_expired(max_age_minutes=30)
        assert count == 0
        payload = await _reload_draft("car3")
        assert payload["generation_pending"] is True
        assert payload["generation_stage"] == "awaiting_callback"
        assert payload["slide_images"][0] is None

    async def test_expired_all_slots_failed(self):
        """All slots expire → every slot marked failed, stage=error, pending=False."""
        from bot.services.kie_task_store import cleanup_expired

        await _insert_draft(
            "car4",
            kind="carousel",
            payload={
                "slides": ["s1", "s2"],
                "img_prompts": ["p1", "p2"],
                "slide_images": [None, None],
                "generation_pending": True,
                "generation_stage": "awaiting_callback",
            },
        )
        await _insert_expired_task("tkn-car4-0", draft_id="car4", content_type="carousel_slide", slot_key="0")
        await _insert_expired_task("tkn-car4-1", draft_id="car4", content_type="carousel_slide", slot_key="1")

        count = await cleanup_expired(max_age_minutes=30)
        assert count == 2
        payload = await _reload_draft("car4")
        assert payload["slide_images"][0]["failed"] is True
        assert payload["slide_images"][1]["failed"] is True
        assert payload["generation_stage"] == "error"
        assert payload["generation_pending"] is False

    async def test_expired_without_draft_id_is_safe(self):
        """Tasks with no draft_id (old orphan rows) must be expired without errors."""
        from bot.services.kie_task_store import cleanup_expired

        await _insert_expired_task("tkn-orphan", draft_id=None, content_type="", slot_key="0")  # type: ignore[arg-type]
        count = await cleanup_expired(max_age_minutes=30)
        assert count == 1


    async def test_expired_does_not_overwrite_already_delivered_url(self):
        """If a slot already has a url (delivered via webhook/manual/recovery),
        a later expired task for the same slot must NOT overwrite it."""
        from bot.services.kie_task_store import cleanup_expired

        await _insert_draft(
            "car_keep",
            kind="carousel",
            payload={
                "slides": ["s1"],
                "img_prompts": ["p1"],
                "slide_images": [{"url": "/real.png", "filename": "real.png"}],
                "generation_pending": False,
                "generation_stage": "",
            },
        )
        await _insert_expired_task("tkn-keep", draft_id="car_keep", content_type="carousel_slide", slot_key="0")

        count = await cleanup_expired(max_age_minutes=30)
        assert count == 1

        payload = await _reload_draft("car_keep")
        assert payload["slide_images"][0] == {"url": "/real.png", "filename": "real.png"}
        # stage stays clean — all slots are delivered.
        assert payload.get("generation_stage", "") != "error"

    async def test_expired_clears_generation_message_and_wakes_sse(self):
        """After cleanup the stale "Генерирую…" message must be cleared and
        SSE listeners must be woken so clients see the error state immediately."""
        import asyncio
        from bot.services.kie_task_store import cleanup_expired
        from miniapp.api.generation._common import _generation_events

        await _insert_draft(
            "car_sse",
            kind="carousel",
            payload={
                "slides": ["s1"],
                "img_prompts": ["p1"],
                "slide_images": [None],
                "generation_pending": True,
                "generation_stage": "awaiting_callback",
                "generation_message": "Генерирую картинки для карусели…",
            },
        )
        await _insert_expired_task("tkn-sse", draft_id="car_sse", content_type="carousel_slide", slot_key="0")

        evt = asyncio.Event()
        _generation_events["car_sse"] = evt

        try:
            count = await cleanup_expired(max_age_minutes=30)
        finally:
            _generation_events.pop("car_sse", None)

        assert count == 1
        assert evt.is_set(), "SSE event must be set so client wakes up"

        payload = await _reload_draft("car_sse")
        assert payload["generation_message"] == ""
        assert payload["generation_stage"] == "error"
        assert payload["generation_pending"] is False


class TestCleanupExpiredReelsLegacy:
    async def test_expired_reels_storyboard_frame(self):
        """content_type='reels_frame' (legacy kind='reels') → storyboard[i]
        carries asset_status='error'."""
        from bot.services.kie_task_store import cleanup_expired

        await _insert_draft(
            "reels_old",
            kind="reels",
            payload={
                "storyboard": [
                    {"text": "frame 0", "current_asset": {"url": "/f0.png"}},
                    {"text": "frame 1"},
                ],
                "generation_pending": True,
                "generation_stage": "awaiting_callback",
            },
        )
        await _insert_expired_task("tkn-reels-old", draft_id="reels_old", content_type="reels_frame", slot_key="1")

        count = await cleanup_expired(max_age_minutes=30)
        assert count == 1

        payload = await _reload_draft("reels_old")
        assert payload["storyboard"][0]["current_asset"]["url"] == "/f0.png"
        assert payload["storyboard"][1]["asset_status"] == "error"
        assert payload["storyboard"][1]["asset_error"] == "timeout"
        assert payload["generation_pending"] is False
        assert payload["generation_stage"] == "error"


class TestCleanupExpiredReelsV2:
    async def test_expired_reels_v2_frame_marked_failed(self):
        from bot.services.kie_task_store import cleanup_expired

        frame_id = "frame-aaa"
        await _insert_draft(
            "r2d1",
            kind="reels_v2",
            payload={
                "frames": [
                    {"id": frame_id, "image_prompt": "p", "image_status": "generating", "image_url": ""},
                    {"id": "frame-bbb", "image_prompt": "p2", "image_status": "ready", "image_url": "/x.png"},
                ],
                "generation_pending": True,
                "generation_stage": "awaiting_callback",
            },
        )
        await _insert_expired_task("tkn-r2-frame", draft_id="r2d1", content_type="reels_v2_frame", slot_key=frame_id)

        count = await cleanup_expired(max_age_minutes=30)
        assert count == 1

        payload = await _reload_draft("r2d1")
        failed_frame = payload["frames"][0]
        assert failed_frame["image_status"] == "error"
        assert failed_frame.get("error_message", "").lower().startswith("timeout") or failed_frame.get("error_message") == "timeout"
        # Second frame stays ready and untouched.
        assert payload["frames"][1]["image_status"] == "ready"
        assert payload["frames"][1]["image_url"] == "/x.png"
        assert payload["generation_pending"] is False
