"""Keyboard: blur, scroll-to-view, desktop keyboard nav."""
from __future__ import annotations

from .helpers import click_bottom_tab, click_draft_card


def test_keyboard_can_open_cards_and_create_tools(desktop_page):
    # Default tab is "drafts" (Вдохновение) — draft cards should be visible
    desktop_page.wait_for_selector(".draft-card", timeout=5000)
    desktop_page.locator(".draft-card").first.focus()
    desktop_page.keyboard.press("Enter")
    desktop_page.locator(".detail-title").wait_for(state="visible", timeout=5000)
    assert desktop_page.locator(".detail-title").is_visible()

    # "Создать" tab removed from strip; navigate via URL param
    base = desktop_page.url.split("?")[0]
    desktop_page.goto(f"{base}?tab=create", wait_until="domcontentloaded")
    desktop_page.wait_for_selector("body.app-ready", timeout=10000)
    desktop_page.locator(".create-card[data-tool='content']").wait_for(state="visible", timeout=5000)
    desktop_page.locator(".create-card[data-tool='content']").focus()
    desktop_page.keyboard.press("Enter")
    desktop_page.locator("[data-create-content]").wait_for(state="visible", timeout=5000)
    assert desktop_page.locator("[data-create-content]").is_visible()


def test_tap_outside_textarea_dismisses_keyboard_focus(page):
    click_bottom_tab(page, "#btnTabCreate")
    page.get_by_role("heading", name="Пост для соцсетей").click()
    page.locator("textarea[name='topic']").wait_for(state="visible", timeout=5000)
    page.locator("textarea[name='topic']").focus()
    assert page.evaluate("document.activeElement && document.activeElement.tagName") == "TEXTAREA"

    page.locator("#detailPanel").click(position={"x": 20, "y": 20})
    page.wait_for_timeout(200)  # blur propagation

    assert page.evaluate("document.activeElement && document.activeElement.tagName") != "TEXTAREA"


def test_focusing_lower_review_field_keeps_it_in_view(page):
    click_bottom_tab(page, "#btnTabInspiration")
    click_draft_card(page, "Как мягко выйти из рабочего напряжения")

    page.evaluate("window.scrollTo(0, 0)")
    page.locator("#contentEditorNotesField").focus()
    page.wait_for_timeout(200)  # focus propagation

    metrics = page.evaluate(
        """
        () => {
          const field = document.getElementById('contentEditorNotesField');
          if (!field) return null;
          const rect = field.getBoundingClientRect();
          const viewportHeight = window.visualViewport?.height || window.innerHeight;
          return {
            top: Math.round(rect.top),
            bottom: Math.round(rect.bottom),
            viewportHeight: Math.round(viewportHeight),
          };
        }
        """
    )

    assert metrics is not None
    assert metrics["top"] >= 0
    assert metrics["bottom"] <= metrics["viewportHeight"]
