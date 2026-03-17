"""Reels: storyboard, frames, regeneration."""
from __future__ import annotations

import json

from .helpers import open_reels_detail_from_drafts


def test_reels_tab_opens_storyboard_without_empty_state(page):
    open_reels_detail_from_drafts(page)

    assert not page.locator("#emptyState").is_visible()
    assert page.locator(".detail-title").inner_text().strip() == "Вечерний ароматический ритуал"

    page.get_by_text("Открыть редактирование кадра").first.click()
    page.wait_for_timeout(100)
    assert page.get_by_role("button", name="Скопировать промпт кадра").is_visible()
    assert page.locator(".frame-image").count() == 1


def test_reels_detail_shows_production_overview_and_frame_status(page):
    open_reels_detail_from_drafts(page)

    assert page.get_by_text("План рилса").is_visible()
    assert page.get_by_text("Shot 1").is_visible()
    assert page.get_by_text("Кадр готов").first.is_visible()
    assert page.get_by_text("Открыть редактирование кадра").first.is_visible()


def test_reels_detail_falls_back_to_payload_storyboard(page):
    def _fulfill_reel(route):
        if not route.request.url.endswith("/api/reels/reels001"):
            route.continue_()
            return
        payload = {
            "draft_id": "reels001",
            "kind": "reels",
            "topic": "Вечерний ароматический ритуал",
            "source": "/miniapp",
            "status": "draft",
            "feedback": "",
            "created_at": "2026-03-11T18:00:00+00:00",
            "preview": "Рилс с fallback-раскадровкой.",
            "images_ready": 1,
            "frame_count": 0,
            "frames": [],
            "payload": {
                "concept": "Вечернее переключение",
                "scenario": "Короткий сценарий",
                "storyboard": [
                    {
                        "timecode": "0-3 сек",
                        "scene": "**Текст на экране:** Попробуй сегодня",
                        "angle": "Крупный план",
                        "current_asset": {
                            "url": "/generated/reels_assets/reels001/frame_1.png",
                            "filename": "frame_1.png",
                        },
                    }
                ],
            },
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))

    page.route("**/api/reels/reels001", _fulfill_reel)
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(100)
    page.get_by_text("Вечерний ароматический ритуал").first.click()
    page.wait_for_timeout(100)

    assert page.locator(".storyboard-frame").count() == 1
    assert page.get_by_text("Попробуй сегодня").first.is_visible()


def test_drafts_reels_card_routes_into_storyboard_detail_with_mocked_api(page):
    reels_detail = {
        "draft_id": "reels001",
        "kind": "reels",
        "topic": "Вечерний ароматический ритуал",
        "source": "/miniapp",
        "status": "draft",
        "feedback": "",
        "created_at": "2026-03-11T18:00:00+00:00",
        "preview": "Рилс с раскадровкой.",
        "images_ready": 1,
        "frame_count": 1,
        "frames": [
            {
                "timecode": "0-3 сек",
                "scene": "Камера идет по флакону и ладони",
                "angle": "Крупный план",
                "gemini_prompt": "close-up bottle and hand, warm evening light",
                "current_asset": {
                    "url": "/generated/reels_assets/reels001/frame_1.png",
                    "filename": "frame_1.png",
                },
            }
        ],
        "payload": {
            "concept": "Вечернее переключение",
            "scenario": "Короткий сценарий",
            "storyboard": [],
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

    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(100)
    page.get_by_text("Вечерний ароматический ритуал").first.click()
    page.wait_for_timeout(100)

    assert page.locator(".storyboard-frame").count() == 1
    assert page.get_by_text("Камера идет по флакону и ладони").first.is_visible()
    assert not page.get_by_text("Превью").is_visible()


def test_reels_and_plans_render_markdown_in_detail_views(page):
    open_reels_detail_from_drafts(page)

    frame_markup = page.locator(".reels-frame-section-value").first.evaluate(
        "(node) => ({ html: node.innerHTML, text: node.textContent })"
    )
    assert "<strong>" in frame_markup["html"]
    assert "<h4>" in frame_markup["html"]
    assert "**Текст на экране:**" not in frame_markup["text"]
    assert "## Сцена" not in frame_markup["text"]

    page.locator("#btnTabPlans").click()
    page.wait_for_timeout(100)
    page.locator(".plan-card").first.click()
    page.wait_for_timeout(100)

    plan_markup = page.locator(".detail-preview.detail-markdown").first.evaluate(
        "(node) => ({ html: node.innerHTML, text: node.textContent })"
    )
    assert "<h4>Контент-план</h4>" in plan_markup["html"]
    assert "<li>Понедельник: Threads</li>" in plan_markup["html"]
    assert "## Контент-план" not in plan_markup["text"]


def test_reels_storyboard_regenerate_enters_pending_images_state(page):
    pending_reel = {
        "draft_id": "reels001",
        "kind": "reels",
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
        "shot_list": [],
        "production_notes": {"required": [], "optional": []},
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
    page.get_by_role("button", name="Пересобрать раскадровку").click()
    page.wait_for_timeout(100)

    assert page.get_by_text("Генерирую кадры для рилса.").count() >= 1
    assert page.get_by_text("0/4 кадров").count() >= 1


def test_themed_reels_detail_renders(themed_page):
    """Reels storyboard renders in both themes."""
    open_reels_detail_from_drafts(themed_page)
    assert themed_page.locator(".detail-title").inner_text().strip() == "Вечерний ароматический ритуал"
    assert themed_page.locator(".storyboard-frame").count() >= 1
