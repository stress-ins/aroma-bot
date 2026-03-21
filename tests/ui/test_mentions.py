"""Mentions: detail view, button visibility, back navigation."""
from __future__ import annotations


def _nav_to_mentions(page):
    """Navigate to Mentions via content sub-tab."""
    page.locator(".content-sub-tab", has_text="Упоминания").click()
    page.wait_for_timeout(500)


def test_mentions_detail_buttons_visible(dark_page):
    """Open mention detail and verify buttons are visible with correct classes."""
    page = dark_page

    # Navigate to Mentions via content sub-tab
    _nav_to_mentions(page)

    # Open first mention detail
    mention_card = page.locator(".mention-card").first
    mention_card.wait_for(state="visible", timeout=5000)
    mention_card.click()
    page.wait_for_timeout(300)

    # Verify back button uses renderBackButton() — .back-button class
    back_btn = page.locator("button.back-button")
    back_btn.wait_for(state="visible", timeout=3000)
    box = back_btn.bounding_box()
    assert box is not None and box["width"] > 0 and box["height"] > 0, "Back button must have non-zero size"

    # Verify generate button is visible and uses correct class
    gen_btn = page.locator("button.primary-button", has_text="Сгенерировать ответы")
    gen_btn.wait_for(state="visible", timeout=3000)
    box = gen_btn.bounding_box()
    assert box is not None and box["width"] > 0 and box["height"] > 0, "Generate button must have non-zero size"

    # Verify ignore button (mention is pending)
    ignore_btn = page.locator("button.secondary-button", has_text="Игнорировать")
    ignore_btn.wait_for(state="visible", timeout=3000)
    box = ignore_btn.bounding_box()
    assert box is not None and box["width"] > 0 and box["height"] > 0, "Ignore button must have non-zero size"

    # Verify no old btn classes remain
    assert page.locator(".btn.btn-primary").count() == 0, "No .btn.btn-primary elements should exist"
    assert page.locator(".btn.btn-ghost").count() == 0, "No .btn.btn-ghost elements should exist"
    assert page.locator("button.ghost-button", has_text="Назад").count() == 0, "No ghost-button back should exist"


def test_mentions_published_reply_state(dark_page):
    """Published mention shows badge, hides publish buttons and generate/ignore."""
    page = dark_page

    # Navigate to Mentions via content sub-tab
    _nav_to_mentions(page)

    # Switch filter to "Отвечено" to see mention002
    page.get_by_text("Отвечено").click()
    page.wait_for_timeout(500)

    # Open the replied mention
    mention_card = page.locator(".mention-card").first
    mention_card.wait_for(state="visible", timeout=5000)
    mention_card.click()
    page.wait_for_timeout(300)

    # Should show "Опубликовано" badge with tone label
    published_badge = page.locator(".tag-status-ok", has_text="Опубликовано")
    published_badge.wait_for(state="visible", timeout=3000)
    assert "Тёплый" in published_badge.text_content(), "Published badge must include tone label"

    # No "Опубликовать" buttons should be visible
    assert page.locator("button", has_text="Опубликовать").count() == 0, \
        "Publish buttons must be hidden after a reply is published"

    # Generate and Ignore buttons should be disabled (status is replied)
    gen_btn = page.locator("button", has_text="Сгенерировать")
    assert gen_btn.count() == 1, "Generate button must be visible but disabled when replied"
    assert gen_btn.is_disabled(), "Generate button must be disabled when status is replied"
    ign_btn = page.locator("button", has_text="Игнорировать")
    assert ign_btn.count() == 1, "Ignore button must be visible but disabled when replied"
    assert ign_btn.is_disabled(), "Ignore button must be disabled when status is replied"


def test_mentions_detail_back_navigation(dark_page):
    """Clicking back button returns to mentions list."""
    page = dark_page

    _nav_to_mentions(page)

    # Open mention
    page.locator(".mention-card").first.wait_for(state="visible", timeout=5000)
    page.locator(".mention-card").first.click()
    page.wait_for_timeout(300)

    # We should see the detail view (generate button present)
    page.locator("button.primary-button", has_text="Сгенерировать").wait_for(state="visible", timeout=3000)

    # Click back via renderBackButton()
    page.locator("button.back-button").click()
    page.wait_for_timeout(300)

    # Should return to list — mention cards visible again
    page.locator(".mention-card").first.wait_for(state="visible", timeout=3000)
