"""Handbook: browsing, search, detail cards."""
from __future__ import annotations

import json


def test_handbook_section_titles_are_russian(page):
    """Topbar title must show Russian name when navigating handbook tabs."""
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(100)

    page.get_by_role("button", name="Смеси").click()
    page.wait_for_timeout(100)
    title = page.locator(".topbar-title").inner_text().strip()
    assert title == "Смеси", f"Expected 'Смеси', got '{title}'"

    page.get_by_role("button", name="Симптомы").click()
    page.wait_for_timeout(100)
    title = page.locator(".topbar-title").inner_text().strip()
    assert title == "Симптомы", f"Expected 'Симптомы', got '{title}'"

    page.get_by_role("button", name="Ароматы").click()
    page.wait_for_timeout(100)
    title = page.locator(".topbar-title").inner_text().strip()
    assert title == "Ароматы", f"Expected 'Ароматы', got '{title}'"


def test_handbook_cards_open_in_all_sections(page):
    """Clicking a card in each handbook section must open the detail view."""
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(100)

    sections = [
        ("Ароматы", "Лаванда"),
        ("Смеси", "Grounding"),
        ("Симптомы", "Стресс"),
        ("Практики", "Квадратное дыхание"),
        ("Звуки", "Гонг"),
    ]

    for tab_label, card_name in sections:
        page.get_by_role("button", name=tab_label).click()
        page.wait_for_timeout(100)

        card = page.locator(".reference-card").filter(has_text=card_name).first
        assert card.is_visible(), f"Card '{card_name}' not found in '{tab_label}' tab"
        card.click()
        page.wait_for_function(
            f"() => (document.querySelector('#draftDetail') || {{innerText: ''}}).innerText.includes({json.dumps(card_name)})",
            timeout=5000,
        )

        detail = page.locator("#draftDetail")
        assert card_name in detail.inner_text(), (
            f"Card '{card_name}' detail did not open (tab: '{tab_label}')"
        )

        back_btn = page.locator("#draftDetail .back-button")
        if back_btn.count() > 0:
            back_btn.first.click()
            page.wait_for_timeout(100)


def test_filter_chips_no_horizontal_overflow(page):
    """Filter chips bar in Symptoms tab must not cause horizontal document overflow."""
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(100)

    page.get_by_role("button", name="Симптомы").click()
    page.wait_for_timeout(100)

    page.wait_for_selector(".filter-chips", timeout=3000)

    chip_count = page.locator(".filter-chip").count()
    assert chip_count >= 2, f"Expected filter chips to render, got {chip_count} chip(s)"

    overflow = page.evaluate("() => document.body.scrollWidth - window.innerWidth")
    assert overflow <= 0, (
        f"Horizontal overflow detected in Symptoms filter chips: +{overflow}px beyond viewport."
    )


def test_themed_handbook_sections_render(themed_page):
    """Handbook sections render in both themes."""
    themed_page.locator("#btnTabHandbook").click()
    themed_page.wait_for_timeout(100)

    themed_page.get_by_role("button", name="Смеси").click()
    themed_page.wait_for_timeout(100)
    assert themed_page.locator(".reference-card").count() >= 1

    themed_page.get_by_role("button", name="Симптомы").click()
    themed_page.wait_for_timeout(100)
    assert themed_page.locator(".reference-card").count() >= 1
