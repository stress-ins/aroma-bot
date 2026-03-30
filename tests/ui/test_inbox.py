"""Inbox: sub-tab renders conversation list, not publications."""
from __future__ import annotations

from .helpers import click_bottom_tab, click_content_sub_tab


def _nav_to_inbox(page):
    """Navigate to Inbox via Контент bottom tab then content sub-tab."""
    click_bottom_tab(page, "#btnTabContent")
    click_content_sub_tab(page, "Входящие")


def test_inbox_subtab_renders_inbox_not_publications(dark_page):
    """Clicking Входящие sub-tab must show inbox content, not publications feed."""
    page = dark_page
    _nav_to_inbox(page)

    # Should show inbox UI elements (conversation card or empty state)
    has_card = page.locator(".inbox-card").count() > 0
    has_empty = page.locator(".empty-state").count() > 0
    has_inbox_summary = page.locator(".inbox-summary").count() > 0

    assert has_card or has_empty or has_inbox_summary, \
        "Inbox tab must render inbox module (cards, summary, or empty state) — not publications"

    # Must NOT show publications feed elements
    assert page.locator(".plans-feed-body .overview-card").count() == 0 or has_card, \
        "Inbox tab must not show publications overview cards"


def test_inbox_conversation_card_visible(dark_page):
    """Inbox shows conversation card with participant name."""
    page = dark_page
    _nav_to_inbox(page)

    card = page.locator(".inbox-card").first
    card.wait_for(state="visible", timeout=5000)

    # Card should contain participant name from fixture
    name = card.locator(".inbox-card-name")
    assert name.count() > 0, "Conversation card must show participant name"

    # Card should contain message preview
    preview = card.locator(".inbox-card-preview")
    assert preview.count() > 0, "Conversation card must show message preview"


def test_inbox_conversation_detail_opens(dark_page):
    """Clicking a conversation card opens chat view with messages."""
    page = dark_page
    _nav_to_inbox(page)

    card = page.locator(".inbox-card").first
    card.wait_for(state="visible", timeout=5000)
    card.click()

    # Should show back button
    back_btn = page.locator("button.back-button")
    back_btn.wait_for(state="visible", timeout=3000)

    # Should show chat bubbles
    bubble = page.locator(".inbox-bubble")
    assert bubble.count() > 0, "Conversation detail must show message bubbles"
