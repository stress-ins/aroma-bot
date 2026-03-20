"""iPad visual snapshot tests.

iPad Pro 11" (834x1194) sits above the 760px mobile breakpoint,
so it renders the desktop split-panel layout. These screenshots
capture how each screen looks at that intermediate width.

Run:     UPDATE_VISUAL_BASELINE=1 .venv/bin/pytest tests/ui/test_ipad_screenshots.py -v -m visual
Compare: ls tests/ui/snapshots/ipad-*
"""
from __future__ import annotations

import pytest

from .helpers import assert_visual_snapshot, prepare_visual_state


def _nav_to_drafts(page):
    """Navigate to drafts list via desktop UI (content sub-switcher)."""
    page.get_by_role("button", name="Черновики").first.click()
    page.wait_for_timeout(200)


def _nav_to_plans(page):
    """Navigate to plans tab (bottom tab bar hidden at iPad width — dispatch click via JS)."""
    page.evaluate("document.getElementById('btnTabPlans').click()")
    page.wait_for_timeout(300)


def _nav_to_handbook(page):
    """Navigate to handbook via desktop mode selector."""
    page.locator("#modeHandbook").click()
    page.wait_for_timeout(200)


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
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(100)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-draft-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_plan_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_plans(page)
    page.locator(".plan-card").first.click()
    page.wait_for_timeout(100)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-plan-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_reels_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_drafts(page)
    page.get_by_text("Вечерний ароматический ритуал").first.click()
    page.wait_for_timeout(100)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-reels-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_threads_series_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_drafts(page)
    page.get_by_text("Восстановление энергии и ресурса").first.click()
    page.wait_for_timeout(100)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-threads-series-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_handbook_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_handbook(page)
    page.wait_for_timeout(200)
    page.locator(".reference-card").first.click()
    page.wait_for_timeout(400)
    prepare_visual_state(page)
    # Handbook detail has non-deterministic icon/text rendering (~5.5% variance)
    assert_visual_snapshot(page.locator(".shell"), "ipad-handbook-detail.png", max_diff_ratio=0.07)


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_carousel_detail(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_drafts(page)
    page.get_by_text("Сенсорная карусель для вечернего ритуала").first.click()
    page.wait_for_timeout(200)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-carousel-detail.png")


@pytest.mark.visual
@pytest.mark.skip_zone_check
def test_ipad_mentions_list(ipad_dark_page):
    page = ipad_dark_page
    _nav_to_plans(page)
    page.get_by_text("Упоминания").click()
    page.wait_for_timeout(300)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "ipad-mentions-list.png")
