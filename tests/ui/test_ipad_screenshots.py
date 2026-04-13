"""iPad visual snapshot tests.

iPad Pro 11" (834x1194) sits above the 760px mobile breakpoint,
so it renders the desktop split-panel layout. These screenshots
capture how each screen looks at that intermediate width.

Run:     UPDATE_VISUAL_BASELINE=1 .venv/bin/pytest tests/ui/test_ipad_screenshots.py -v -m visual
Compare: ls tests/ui/snapshots/ipad-*
"""
from __future__ import annotations

import pytest

from .helpers import (
    assert_visual_snapshot,
    click_bottom_tab,
    click_content_sub_tab,
    click_draft_card,
    prepare_visual_state,
)


def _nav_to_drafts(page):
    """Navigate to drafts list via Вдохновение bottom tab."""
    click_bottom_tab(page, "#btnTabInspiration")


def _nav_to_plans(page):
    """Navigate to plans via Контент bottom tab + Планы sub-tab."""
    click_bottom_tab(page, "#btnTabContent")
    click_content_sub_tab(page, "Планы")


def _nav_to_handbook(page):
    """Navigate to handbook (dispatch click via JS — mode-selector hidden on mobile layout)."""
    page.evaluate("document.getElementById('modeHandbook').click()")
    page.locator(".reference-card").first.wait_for(state="visible", timeout=10000)


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_drafts_list(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_drafts(page)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-drafts-list.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_draft_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_drafts(page)
    click_draft_card(page, "Как мягко выйти из рабочего напряжения")
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-draft-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_plan_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_plans(page)
    page.locator(".plan-card").first.wait_for(state="visible", timeout=10000)
    page.locator(".plan-card").first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-plan-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_reels_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_drafts(page)
    click_draft_card(page, "Вечерний ароматический ритуал")
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-reels-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_threads_series_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_drafts(page)
    click_draft_card(page, "Восстановление энергии и ресурса")
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-threads-series-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_handbook_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_handbook(page)
    page.locator(".reference-card").first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)
    prepare_visual_state(page)
    # Handbook detail has non-deterministic icon/text rendering (~5.5% variance)
    assert_visual_snapshot(page.locator(".shell"), "ipad-handbook-detail.png", max_diff_ratio=0.07)


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_carousel_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_drafts(page)
    click_draft_card(page, "Сенсорная карусель для вечернего ритуала")
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-carousel-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_mentions_list(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_plans(page)
    page.get_by_text("Упоминания").click()
    page.locator(".mention-card").first.wait_for(state="visible", timeout=5000)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-mentions-list.png")
