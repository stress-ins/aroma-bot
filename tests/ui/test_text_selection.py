"""Verify interactive elements block text selection on mobile (long-press UX bug)."""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

# Interactive elements that MUST have user-select: none
INTERACTIVE_CHECKS = [
    (".bottom-tab-btn", "Bottom tab bar buttons"),
    (".tab-button", "Top horizontal tabs"),
    ("button.primary-button", "Primary buttons"),
    ("button.secondary-button", "Secondary buttons"),
    (".interactive-card", "Interactive cards"),
    (".date-picker-btn", "Date picker buttons"),
]

# Content elements that MUST remain selectable (user-select: text or auto)
SELECTABLE_CHECKS = [
    ("textarea", "Textarea inputs"),
    (".detail-preview", "Draft preview text"),
    (".detail-markdown", "Markdown content"),
]


def _get_user_select(page: Page, selector: str) -> list[dict]:
    """Return computed user-select for visible elements matching selector."""
    return page.evaluate("""(sel) => {
        const els = document.querySelectorAll(sel);
        return Array.from(els).map(el => {
            const s = getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return null;
            return {
                text: (el.textContent || '').trim().slice(0, 40),
                userSelect: s.userSelect || s.webkitUserSelect || 'auto',
                tag: el.tagName.toLowerCase()
            };
        }).filter(Boolean).filter(e => e.text.length > 0);
    }""", selector)


@pytest.mark.parametrize("selector,name", INTERACTIVE_CHECKS, ids=[s for s, _ in INTERACTIVE_CHECKS])
def test_interactive_elements_not_selectable(page: Page, selector: str, name: str):
    """Interactive elements must have user-select: none to prevent mobile long-press selection."""
    elements = _get_user_select(page, selector)
    if not elements:
        pytest.skip(f"No '{selector}' elements found on page")

    bad = [el for el in elements if el["userSelect"] != "none"]
    assert not bad, (
        f"\n[{name}] Elements allowing text selection:\n"
        + "\n".join(f"  <{e['tag']}> '{e['text']}' → user-select: {e['userSelect']}" for e in bad)
        + f"\n\nFix: add user-select: none to '{selector}'"
    )


@pytest.mark.parametrize("selector,name", SELECTABLE_CHECKS, ids=[s for s, _ in SELECTABLE_CHECKS])
def test_content_remains_selectable(page: Page, selector: str, name: str):
    """Content text and inputs must stay selectable — users copy text and use inputs."""
    elements = _get_user_select(page, selector)
    if not elements:
        pytest.skip(f"No '{selector}' elements found on page")

    bad = [el for el in elements if el["userSelect"] == "none"]
    assert not bad, (
        f"\n[{name}] Content blocked from selection:\n"
        + "\n".join(f"  <{e['tag']}> '{e['text']}'" for e in bad)
        + f"\n\nFix: add user-select: text to '{selector}'"
    )


def test_tap_highlight_transparent_on_buttons(page: Page):
    """-webkit-tap-highlight-color must be transparent on buttons."""
    results = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('button, .bottom-tab-btn, .tab-button')).map(el => {
            const s = getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return null;
            return {
                text: (el.textContent || '').trim().slice(0, 30),
                tapColor: s.webkitTapHighlightColor || ''
            };
        }).filter(Boolean).filter(e => e.text.length > 0).slice(0, 15);
    }""")

    bad = [r for r in results if r["tapColor"] not in ("rgba(0, 0, 0, 0)", "transparent", "rgba(0,0,0,0)", "")]
    assert not bad, (
        "\nButtons with visible tap-highlight (blue/gray flash on tap):\n"
        + "\n".join(f"  '{r['text']}' → tap-highlight: {r['tapColor']}" for r in bad)
        + "\n\nFix: -webkit-tap-highlight-color: transparent"
    )
