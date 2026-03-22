"""Archive screen: tab navigation, card display, detail view, form."""
from __future__ import annotations


def _nav_to_archive(page):
    """Navigate to Archive via Контент bottom tab then content sub-tab."""
    # Click the Контент bottom tab button to enter the plans/content area
    content_btn = page.locator("#btnTabContent")
    content_btn.wait_for(state="visible", timeout=5000)
    content_btn.click()
    page.wait_for_timeout(1000)
    page.locator(".content-sub-tab", has_text="Архив").click()
    page.wait_for_timeout(800)


def test_archive_tab_visible(dark_page):
    """Archive tab appears as a content sub-tab under Контент."""
    page = dark_page
    content_btn = page.locator("#btnTabContent")
    content_btn.wait_for(state="visible", timeout=5000)
    content_btn.click()
    page.wait_for_timeout(1000)
    archive_tab = page.locator(".content-sub-tab", has_text="Архив")
    archive_tab.wait_for(state="visible", timeout=5000)
    assert archive_tab.is_visible()


def test_archive_list_loads(dark_page):
    """Switching to Archive tab shows list of past publications."""
    page = dark_page
    _nav_to_archive(page)

    cards = page.locator(".archive-card")
    cards.first.wait_for(state="visible", timeout=5000)
    assert cards.count() >= 2


def test_archive_card_has_metrics(dark_page):
    """Archive cards display engagement metrics."""
    page = dark_page
    _nav_to_archive(page)

    first_card = page.locator(".archive-card").first
    first_card.wait_for(state="visible", timeout=5000)
    metrics = first_card.locator(".archive-card-metrics")
    assert metrics.is_visible()


def test_archive_detail_opens(dark_page):
    """Clicking an archive card opens detail view with scoring section."""
    page = dark_page
    _nav_to_archive(page)

    first_card = page.locator(".archive-card").first
    first_card.wait_for(state="visible", timeout=5000)
    first_card.click()
    page.wait_for_timeout(2000)

    # On mobile, detail view should now contain scoring section
    detail_html = page.locator("#draftDetail").inner_html()
    assert "ОЦЕНКА" in detail_html or "score-stars-row" in detail_html, f"Detail should contain scoring. Got: {detail_html[:200]}"


def test_archive_add_button(dark_page):
    """Add publication button is visible in archive list."""
    page = dark_page
    _nav_to_archive(page)

    add_btn = page.locator("button", has_text="Добавить публикацию")
    add_btn.wait_for(state="visible", timeout=3000)
    assert add_btn.is_visible()


def test_archive_form_opens(dark_page):
    """Clicking add button opens archive form with URL import and save."""
    page = dark_page
    _nav_to_archive(page)

    page.locator("button", has_text="Добавить публикацию").click()
    page.wait_for_timeout(2000)

    # Detail panel should contain form elements
    detail_html = page.locator("#draftDetail").inner_html()
    assert "archiveImportUrl" in detail_html or "Сохранить" in detail_html, f"Form should appear in detail. Got: {detail_html[:200]}"


def test_archive_stats_section(dark_page):
    """Archive list shows statistics section when publications exist."""
    page = dark_page
    _nav_to_archive(page)

    stats = page.locator(".archive-stats")
    stats.wait_for(state="visible", timeout=5000)
    assert stats.is_visible()
    assert "публикаций" in stats.inner_text().lower()
