"""Reels: V2 storyboard, frames, regeneration."""
from __future__ import annotations

import json

from .helpers import click_bottom_tab, click_content_sub_tab, click_draft_card, open_reels_detail_from_drafts


def test_reels_tab_opens_storyboard_without_empty_state(page):
    open_reels_detail_from_drafts(page)

    assert not page.locator("#emptyState").is_visible()
    assert page.locator(".detail-title").inner_text().strip() == "Вечерний ароматический ритуал"

    # V2 renders frames directly — check frame card
    assert page.locator(".reels-frame-v2").count() >= 1


def test_reels_detail_shows_v2_concept_scenario_and_frames(page):
    open_reels_detail_from_drafts(page)

    assert page.get_by_text("Вечернее переключение через ароматический ритуал").first.is_visible()
    assert page.get_by_text("Перегенерировать концепцию").is_visible()
    assert page.get_by_text("Перегенерировать сценарий").is_visible()
    assert page.locator(".reels-frame-v2").count() >= 1


def test_reels_detail_shows_v2_stepper(page):
    open_reels_detail_from_drafts(page)

    assert page.locator(".reels-stepper").count() >= 1
    assert page.locator(".reels-step").count() >= 3


def test_drafts_reels_card_routes_into_storyboard_detail_with_mocked_api(page):
    reels_detail = {
        "draft_id": "reels001",
        "kind": "reels_v2",
        "topic": "Вечерний ароматический ритуал",
        "source": "/miniapp",
        "status": "draft",
        "feedback": "",
        "created_at": "2026-03-11T18:00:00+00:00",
        "preview": "Рилс с раскадровкой.",
        "images_ready": 1,
        "frame_count": 1,
        "concept": "Вечернее переключение",
        "scenario": "Короткий сценарий",
        "caption": "Попробуй вечерний ритуал",
        "frames": [
            {
                "id": "f1",
                "frame_id": "f1",
                "timecode": "0-3 сек",
                "overlay_text": "Камера идет по флакону и ладони",
                "image_prompt": "close-up bottle and hand, warm evening light",
                "image_status": "ready",
                "image_url": "/generated/reels_assets/reels001/frame_1.png",
            }
        ],
        "payload": {
            "concept": "Вечернее переключение",
            "scenario": "Короткий сценарий",
        },
    }

    def _draft_detail(route):
        if route.request.url.endswith("/api/drafts/reels001"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(reels_detail, ensure_ascii=False))
            return
        route.continue_()

    def _reel_detail(route):
        if route.request.url.endswith("/api/reels/reels001"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(reels_detail, ensure_ascii=False))
            return
        route.continue_()

    page.route("**/api/drafts/reels001", _draft_detail)
    page.route("**/api/reels/reels001", _reel_detail)

    click_bottom_tab(page, "#btnTabInspiration")
    click_draft_card(page, "Вечерний ароматический ритуал")

    assert page.locator(".reels-frame-v2").count() == 1
    assert page.get_by_text("Камера идет по флакону и ладони").first.is_visible()


def test_reels_and_plans_render_markdown_in_detail_views(page):
    """Plans still render markdown correctly; reels use V2 inline layout."""
    click_bottom_tab(page, "#btnTabContent")
    click_content_sub_tab(page, "Планы")
    page.locator(".plan-card").first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)

    plan_markup = page.locator(".detail-preview.detail-markdown").first.evaluate(
        "(node) => ({ html: node.innerHTML, text: node.textContent })"
    )
    assert "<h4>Контент-план</h4>" in plan_markup["html"]
    assert "<li>Понедельник: Threads</li>" in plan_markup["html"]
    assert "## Контент-план" not in plan_markup["text"]


def test_reels_storyboard_regenerate_enters_pending_images_state(page):
    pending_reel = {
        "draft_id": "reels001",
        "kind": "reels_v2",
        "topic": "Вечерний ароматический ритуал",
        "source": "/miniapp",
        "status": "draft",
        "feedback": "",
        "created_at": "2026-03-11T18:00:00+00:00",
        "preview": "Короткий сценарий рилса про вечернее переключение.",
        "scenario": "Обновленный сценарий",
        "frame_count": 4,
        "images_ready": 0,
        "generation_pending": True,
        "generation_stage": "images",
        "generation_message": "Генерирую кадры для рилса.",
        "frames": [],
        "payload": {},
    }

    def handle_route(route):
        url = route.request.url
        if url.endswith("/api/reels/reels001/storyboard/regenerate"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(pending_reel, ensure_ascii=False))
            return
        if url.endswith("/api/reels/reels001"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(pending_reel, ensure_ascii=False))
            return
        route.continue_()

    page.route("**/*", handle_route)
    open_reels_detail_from_drafts(page)

    # V2 Screen2 shows generating state with skeleton bars
    assert page.get_by_text("Генерирую кадры для рилса.").count() >= 1


def test_themed_reels_detail_renders(themed_page):
    """Reels V2 detail renders in both themes."""
    open_reels_detail_from_drafts(themed_page)
    assert themed_page.locator(".detail-title").inner_text().strip() == "Вечерний ароматический ритуал"
    assert themed_page.locator(".reels-frame-v2").count() >= 1
