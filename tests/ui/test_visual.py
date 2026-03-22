"""Visual snapshot comparison tests.

These tests are NOT run on CI — use `@pytest.mark.visual` marker.
Run locally with: pytest tests/ui/test_visual.py -m visual
Update baselines: UPDATE_VISUAL_BASELINE=1 pytest tests/ui/test_visual.py -m visual
"""
from __future__ import annotations

import pytest

from .helpers import assert_visual_snapshot, open_reels_detail_from_drafts, prepare_visual_state


@pytest.mark.visual
def test_visual_mobile_drafts_list_baseline(page):
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator(".shell"), "mobile-drafts-list.png")


@pytest.mark.visual
def test_visual_mobile_draft_detail_baseline(page):
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    page.wait_for_timeout(100)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-draft-detail.png")


@pytest.mark.visual
def test_visual_mobile_plan_detail_baseline(page):
    page.locator("#btnTabContent").click()
    page.wait_for_timeout(100)
    page.locator(".content-sub-tab", has_text="Планы").click()
    page.wait_for_timeout(100)
    page.locator(".plan-card").first.click()
    page.wait_for_timeout(100)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-plan-detail.png")


@pytest.mark.visual
def test_visual_mobile_reels_detail_baseline(page):
    open_reels_detail_from_drafts(page)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-reels-detail.png")


@pytest.mark.visual
def test_visual_mobile_threads_series_detail_baseline(page):
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    page.get_by_text("Восстановление энергии и ресурса").first.click()
    page.wait_for_timeout(100)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-threads-series-detail.png")


@pytest.mark.visual
def test_visual_mobile_handbook_detail_baseline(page):
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(100)
    page.locator(".reference-card").first.click()
    page.wait_for_timeout(200)
    prepare_visual_state(page)
    assert_visual_snapshot(page.locator("#detailPanel"), "mobile-handbook-detail.png")


@pytest.mark.visual
def test_visual_desktop_split_view_baseline(desktop_page):
    desktop_page.locator("#btnTabContent").click()
    desktop_page.wait_for_timeout(100)
    desktop_page.locator(".content-sub-tab", has_text="Публикации").click()
    desktop_page.wait_for_timeout(100)
    desktop_page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    desktop_page.wait_for_timeout(100)
    prepare_visual_state(desktop_page)
    assert_visual_snapshot(desktop_page.locator(".shell"), "desktop-split-view.png")
