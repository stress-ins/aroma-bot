"""Tests that a failed carousel slot is serialised through to the mini-app
client intact. The UI uses img.failed === true to render the retry plate
(see miniapp/static/js/carousel.js)."""
from __future__ import annotations


async def _insert_carousel(draft_id: str, payload: dict) -> None:
    from db.models import DraftModel
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        s.add(DraftModel(
            draft_id=draft_id,
            kind="carousel",
            topic="Карусель со сбойным слайдом",
            source="test",
            status="draft",
            feedback="",
            payload=payload,
        ))
        await s.commit()


class TestSerializedFailedSlot:
    async def test_failed_slot_survives_serialisation(self):
        from bot.services.drafts_store import get_draft
        from bot.services.miniapp_presenter import serialize_draft

        await _insert_carousel(
            "failed_draft_1",
            {
                "slides": ["ok slide", "broken slide"],
                "img_prompts": ["p1", "p2"],
                "slide_images": [
                    {"url": "/a.png", "filename": "a.png"},
                    {"failed": True, "error": "timeout", "prompt": "p2"},
                ],
                "generation_pending": False,
                "generation_stage": "error",
            },
        )

        draft = await get_draft("failed_draft_1")
        assert draft is not None
        serialized = await serialize_draft(draft)

        payload = serialized["payload"]
        assert serialized["generation_stage"] == "error"
        assert serialized["generation_pending"] is False
        slides = payload["slide_images"]
        assert slides[0]["url"] == "/a.png"
        assert slides[1]["failed"] is True
        assert slides[1]["error"] == "timeout"
        assert slides[1]["prompt"] == "p2"
