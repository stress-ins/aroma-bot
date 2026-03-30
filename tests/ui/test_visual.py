"""Visual snapshot comparison tests.

These tests are NOT run on CI — use `@pytest.mark.visual` marker.
Run locally with: pytest tests/ui/test_visual.py -m visual
Update baselines: UPDATE_VISUAL_BASELINE=1 pytest tests/ui/test_visual.py -m visual
"""
from __future__ import annotations

import pytest

from .helpers import (
    assert_visual_snapshot,
    click_bottom_tab,
    click_content_sub_tab,
    click_draft_card,
    open_reels_detail_from_drafts,
    prepare_visual_state,
)


@pytest.mark.visual
def test_visual_mobile_drafts_list_baseline(page):
    click_bottom_tab(page, "#btnTabInspiration")
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "mobile-drafts-list.png")


@pytest.mark.visual
def test_visual_mobile_draft_detail_baseline(page):
    click_bottom_tab(page, "#btnTabInspiration")
    click_draft_card(page, "Как мягко выйти из рабочего напряжения")
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-draft-detail.png")


@pytest.mark.visual
def test_visual_mobile_plan_detail_baseline(page):
    click_bottom_tab(page, "#btnTabContent")
    click_content_sub_tab(page, "Планы")
    page.locator(".plan-card").first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-plan-detail.png")


@pytest.mark.visual
def test_visual_mobile_reels_detail_baseline(page):
    open_reels_detail_from_drafts(page)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-reels-detail.png")


@pytest.mark.visual
def test_visual_mobile_threads_series_detail_baseline(page):
    click_bottom_tab(page, "#btnTabInspiration")
    click_draft_card(page, "Восстановление энергии и ресурса")
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-threads-series-detail.png")


@pytest.mark.visual
def test_visual_mobile_handbook_detail_baseline(page):
    click_bottom_tab(page, "#btnTabHandbook")
    page.locator(".reference-card").first.wait_for(state="visible", timeout=10000)
    page.locator(".reference-card").first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-handbook-detail.png")


@pytest.mark.visual
def test_visual_desktop_split_view_baseline(desktop_page):
    # Desktop: wait for app to bootstrap, then open first draft
    desktop_page.wait_for_selector(".draft-card", timeout=10000)
    desktop_page.locator(".draft-card").first.click()
    desktop_page.locator("#draftDetail").wait_for(state="visible", timeout=5000)
    prepare_visual_state(desktop_page)
    assert_visual_snapshot(desktop_page.locator(".shell"), "desktop-split-view.png")
