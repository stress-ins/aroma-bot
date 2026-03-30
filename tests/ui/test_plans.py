"""Plans: list, detail, linked draft creation."""
from __future__ import annotations

import json

from .helpers import click_bottom_tab, click_content_sub_tab


def test_plan_detail_allows_creating_and_opening_linked_draft(page):
    updated_plan = {
        "plan_id": "20260311180000",
        "created_at": "2026-03-11T18:00:00+00:00",
        "raw_text": "Понедельник: Threads, Среда: Reels",
        "entries": [
            {
                "day_label": "Понедельник",
                "platform": "Threads",
                "format_label": "пост",
                "goal": "Доверие",
                "topic": "Почему вечерний ритуал помогает нервной системе",
                "angle": "Через простые телесные сигналы.",
            }
        ],
        "related_drafts": [
            {
                "draft_id": "planth01",
                "kind": "threads",
                "topic": "Почему вечерний ритуал помогает нервной системе",
                "status": "draft",
            }
        ],
    }
    created_draft = {
        "draft_id": "planth01",
        "kind": "threads",
        "topic": "Почему вечерний ритуал помогает нервной системе",
        "source": "/plan",
        "status": "draft",
        "feedback": "",
        "created_at": "2026-03-12T02:00:00+00:00",
        "preview": "Иногда телу нужен сигнал безопасности.",
        "slides_count": 0,
        "storyboard_count": 0,
        "payload": {
            "angle": "Через простые телесные сигналы.",
            "hook": "Иногда телу нужен сигнал безопасности.",
            "caption": "Текст для Threads.",
            "cta": "Напиши, если хочешь разбор.",
            "visual_prompt": "warm evening ritual",
        },
    }

    def handle_route(route):
        url = route.request.url
        if url.endswith("/api/plans/20260311180000/generate"):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"kind": "draft", "draft": created_draft}, ensure_ascii=False),
            )
            return
        if url.endswith("/api/plans?limit=20"):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"items": [updated_plan], "total": 1}, ensure_ascii=False),
            )
            return
        if url.endswith("/api/plans/20260311180000"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(updated_plan, ensure_ascii=False))
            return
        if "/api/drafts?" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "items": [
                            {
                                "draft_id": created_draft["draft_id"],
                                "kind": created_draft["kind"],
                                "topic": created_draft["topic"],
                                "source": created_draft["source"],
                                "created_at": created_draft["created_at"],
                                "status": created_draft["status"],
                                "feedback": "",
                                "preview": created_draft["preview"],
                                "slides_count": 0,
                                "storyboard_count": 0,
                                "images_ready": 0,
                                "generation_pending": False,
                            }
                        ],
                        "total": 1,
                    },
                    ensure_ascii=False,
                ),
            )
            return
        if url.endswith("/api/drafts/planth01"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(created_draft, ensure_ascii=False))
            return
        route.continue_()

    page.route("**/*", handle_route)
    click_bottom_tab(page, "#btnTabContent")
    click_content_sub_tab(page, "Планы")

    page.locator(".plan-card").first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)

    assert page.get_by_role("button", name="Создать Тредс").is_visible()
    page.get_by_role("button", name="Создать Тредс").click()

    # After async generation UX: navigates directly to draft detail on drafts tab
    # Wait for the new title (not the plan title) — poll until content changes
    page.locator(".detail-title", has_text="Почему вечерний ритуал помогает нервной системе").wait_for(
        state="visible", timeout=10000,
    )
    assert page.locator(".detail-title").inner_text().strip() == "Почему вечерний ритуал помогает нервной системе"
    assert page.locator("#btnTabInspiration").get_attribute("class")
