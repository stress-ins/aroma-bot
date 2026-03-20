"""Mentions: detail view, button visibility, back navigation."""
from __future__ import annotations


def test_mentions_detail_buttons_visible(dark_page):
    """Open mention detail and verify buttons are visible with correct classes."""
    page = dark_page

    # Navigate to Plans tab
    page.locator("#btnTabPlans").click()
    page.wait_for_timeout(300)

    # Switch to Упоминания subtab
    page.get_by_text("Упоминания").click()
    page.wait_for_timeout(500)

    # Open first mention detail
    mention_card = page.locator(".mention-card").first
    mention_card.wait_for(state="visible", timeout=5000)
    mention_card.click()
    page.wait_for_timeout(300)

    # Verify back button is visible and uses correct class
    back_btn = page.locator("button.ghost-button", has_text="Назад")
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


def test_mentions_published_reply_state(dark_page):
    """Published mention shows badge, hides publish buttons and generate/ignore."""
    page = dark_page

    # Navigate to Plans tab → Упоминания
    page.locator("#btnTabPlans").click()
    page.wait_for_timeout(300)
    page.get_by_text("Упоминания").click()
    page.wait_for_timeout(500)

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

    # Generate and Ignore buttons should be hidden (status is replied, not pending)
    assert page.locator("button", has_text="Сгенерировать").count() == 0, \
        "Generate button must be hidden when status is not pending"
    assert page.locator("button", has_text="Игнорировать").count() == 0, \
        "Ignore button must be hidden when status is not pending"


def test_mentions_detail_back_navigation(dark_page):
    """Clicking back button returns to mentions list."""
    page = dark_page

    page.locator("#btnTabPlans").click()
    page.wait_for_timeout(300)

    page.get_by_text("Упоминания").click()
    page.wait_for_timeout(500)

    # Open mention
    page.locator(".mention-card").first.wait_for(state="visible", timeout=5000)
    page.locator(".mention-card").first.click()
    page.wait_for_timeout(300)

    # We should see the detail view (generate button present)
    page.locator("button.primary-button", has_text="Сгенерировать").wait_for(state="visible", timeout=3000)

    # Click back
    page.locator("button.ghost-button", has_text="Назад").click()
    page.wait_for_timeout(300)

    # Should return to list — mention cards visible again
    page.locator(".mention-card").first.wait_for(state="visible", timeout=3000)
