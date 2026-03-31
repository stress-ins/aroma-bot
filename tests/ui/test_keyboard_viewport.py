"""Keyboard viewport: verify input fields stay visible when soft keyboard opens.

Simulates the mobile soft keyboard by shrinking visualViewport height,
then checks that focused fields remain within the visible area.
"""
from __future__ import annotations

import pytest

from .helpers import DOM_RENDER, ANIMATION, click_bottom_tab, click_draft_card


# ---------------------------------------------------------------------------
# Helper: simulate keyboard open / close
# ---------------------------------------------------------------------------

_SIMULATE_KEYBOARD_OPEN = """
() => {
  // Shrink visualViewport to simulate keyboard covering ~40% of screen
  const kbHeight = Math.round(window.innerHeight * 0.4);
  const visibleH = window.innerHeight - kbHeight;

  // Patch visualViewport.height to return the reduced value
  Object.defineProperty(window.visualViewport, 'height', {
    value: visibleH,
    writable: true,
    configurable: true,
  });

  // Fire resize event so the app reacts (sets --vv-height, is-keyboard-open)
  window.visualViewport.dispatchEvent(new Event('resize'));
  return visibleH;
}
"""

_SIMULATE_KEYBOARD_CLOSE = """
() => {
  Object.defineProperty(window.visualViewport, 'height', {
    value: window.innerHeight,
    writable: true,
    configurable: true,
  });
  window.visualViewport.dispatchEvent(new Event('resize'));
}
"""

_FIELD_METRICS_JS = """
(selector) => {
  const field = typeof selector === 'string'
    ? document.querySelector(selector)
    : document.activeElement;
  if (!field) return null;
  const rect = field.getBoundingClientRect();
  const visibleH = window.visualViewport?.height || window.innerHeight;
  return {
    tag: field.tagName,
    id: field.id || '',
    top: Math.round(rect.top),
    bottom: Math.round(rect.bottom),
    visibleHeight: Math.round(visibleH),
  };
}
"""


def _assert_field_in_view(page, selector=None):
    """Assert the focused (or selected) field is within the visible viewport."""
    metrics = page.evaluate(_FIELD_METRICS_JS, selector)
    assert metrics is not None, f"Field not found: {selector}"
    assert metrics["bottom"] <= metrics["visibleHeight"], (
        f"Field {metrics['tag']}#{metrics['id']} bottom ({metrics['bottom']}px) "
        f"exceeds visible viewport ({metrics['visibleHeight']}px) — hidden by keyboard"
    )
    assert metrics["top"] >= 0, (
        f"Field {metrics['tag']}#{metrics['id']} top ({metrics['top']}px) clipped above viewport"
    )


def _open_keyboard(page):
    """Simulate keyboard open and wait for animation."""
    page.evaluate(_SIMULATE_KEYBOARD_OPEN)
    page.wait_for_timeout(ANIMATION)


def _close_keyboard(page):
    """Simulate keyboard close."""
    page.evaluate(_SIMULATE_KEYBOARD_CLOSE)


# ---------------------------------------------------------------------------
# Tests: Create tab — topic textarea
# ---------------------------------------------------------------------------

def test_create_topic_field_visible_with_keyboard(page):
    """Create -> content form: topic textarea stays visible when keyboard opens."""
    click_bottom_tab(page, "#btnTabCreate")
    page.get_by_role("heading", name="Пост для соцсетей").click()
    page.locator("textarea[name='topic']").wait_for(state="visible", timeout=5000)

    textarea = page.locator("textarea[name='topic']")
    textarea.focus()
    page.wait_for_timeout(DOM_RENDER)

    _open_keyboard(page)
    _assert_field_in_view(page, "textarea[name='topic']")
    _close_keyboard(page)


# ---------------------------------------------------------------------------
# Tests: Draft detail — editor notes field
# ---------------------------------------------------------------------------

def test_draft_editor_notes_visible_with_keyboard(page):
    """Draft detail: editor notes textarea stays visible when keyboard opens."""
    click_bottom_tab(page, "#btnTabInspiration")

    # Open first draft
    card = page.locator(".draft-card").first
    card.wait_for(state="visible", timeout=5000)
    card.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)

    notes = page.locator("#contentEditorNotesField")
    if not notes.is_visible():
        pytest.skip("Draft has no editor notes field")

    notes.focus()
    page.wait_for_timeout(DOM_RENDER)

    _open_keyboard(page)
    _assert_field_in_view(page, "#contentEditorNotesField")
    _close_keyboard(page)


# ---------------------------------------------------------------------------
# Tests: Settings — brand page forbidden phrases input
# ---------------------------------------------------------------------------

def test_settings_brand_input_visible_with_keyboard(page):
    """Settings -> Brand: forbidden phrase input stays visible with keyboard."""
    click_bottom_tab(page, "#btnTabSettings")
    page.get_by_text("Фирменный стиль").click()
    page.locator("#forbiddenPhraseInput").wait_for(state="visible", timeout=5000)

    input_el = page.locator("#forbiddenPhraseInput")
    if not input_el.is_visible():
        pytest.skip("Forbidden phrase input not visible")

    input_el.focus()
    page.wait_for_timeout(DOM_RENDER)

    _open_keyboard(page)
    _assert_field_in_view(page, "#forbiddenPhraseInput")
    _close_keyboard(page)


# ---------------------------------------------------------------------------
# Tests: Settings — tracked hashtags input
# ---------------------------------------------------------------------------

def test_settings_hashtag_input_visible_with_keyboard(page):
    """Settings -> Hashtags: tag input stays visible with keyboard."""
    click_bottom_tab(page, "#btnTabSettings")
    page.get_by_text("Теги для мониторинга").click()

    input_el = page.locator("#trackedTagInput")
    if not input_el.is_visible():
        pytest.skip("Tracked tag input not visible")

    input_el.focus()
    page.wait_for_timeout(DOM_RENDER)

    _open_keyboard(page)
    _assert_field_in_view(page, "#trackedTagInput")
    _close_keyboard(page)


# ---------------------------------------------------------------------------
# Tests: Settings — monitored accounts input
# ---------------------------------------------------------------------------

def test_settings_monitored_instagram_input_visible_with_keyboard(page):
    """Settings -> Monitored accounts: Instagram input stays visible with keyboard."""
    click_bottom_tab(page, "#btnTabSettings")
    page.get_by_text("Аккаунты на мониторинг").click()

    input_el = page.locator("#monitoredInstagramInput")
    if not input_el.is_visible():
        pytest.skip("Monitored Instagram input not visible")

    input_el.focus()
    page.wait_for_timeout(DOM_RENDER)

    _open_keyboard(page)
    _assert_field_in_view(page, "#monitoredInstagramInput")
    _close_keyboard(page)


def test_settings_monitored_threads_input_visible_with_keyboard(page):
    """Settings -> Monitored accounts: Threads input stays visible with keyboard."""
    click_bottom_tab(page, "#btnTabSettings")
    page.get_by_text("Аккаунты на мониторинг").click()

    input_el = page.locator("#monitoredThreadsInput")
    if not input_el.is_visible():
        pytest.skip("Monitored Threads input not visible")

    # Scroll down to reach Threads section
    page.evaluate("""
      document.getElementById('monitoredThreadsInput')
        ?.scrollIntoView({behavior: 'auto', block: 'center'})
    """)
    page.wait_for_timeout(DOM_RENDER)

    input_el.focus()
    page.wait_for_timeout(DOM_RENDER)

    _open_keyboard(page)
    _assert_field_in_view(page, "#monitoredThreadsInput")
    _close_keyboard(page)


# ---------------------------------------------------------------------------
# Tests: Settings — promo code input
# ---------------------------------------------------------------------------

def test_settings_promo_input_visible_with_keyboard(page):
    """Settings -> Promo: promo code input stays visible with keyboard."""
    click_bottom_tab(page, "#btnTabSettings")
    page.get_by_text("Подписка").first.click()

    input_el = page.locator("#promoCodeInput")
    if not input_el.is_visible():
        pytest.skip("Promo code input not visible")

    input_el.focus()
    page.wait_for_timeout(DOM_RENDER)

    _open_keyboard(page)
    _assert_field_in_view(page, "#promoCodeInput")
    _close_keyboard(page)


# ---------------------------------------------------------------------------
# Tests: Search filter input
# ---------------------------------------------------------------------------

def test_draft_search_input_visible_with_keyboard(page):
    """Drafts list: search filter input stays visible with keyboard."""
    click_bottom_tab(page, "#btnTabInspiration")

    search = page.locator("#queryFilter")
    if not search.is_visible():
        pytest.skip("Search filter not visible")

    search.focus()
    page.wait_for_timeout(DOM_RENDER)

    _open_keyboard(page)
    _assert_field_in_view(page, "#queryFilter")
    _close_keyboard(page)


# ---------------------------------------------------------------------------
# Tests: keyboard-open class toggles body height
# ---------------------------------------------------------------------------

def test_keyboard_open_sets_vv_height_property(page):
    """Verify that the visualViewport resize handler sets --vv-height on body."""
    click_bottom_tab(page, "#btnTabInspiration")

    card = page.locator(".draft-card").first
    card.wait_for(state="visible", timeout=10000)
    card.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)

    # Simulate keyboard by patching visualViewport.height and firing resize
    _open_keyboard(page)

    # --vv-height should be set on body as inline style by the JS handler
    vv = page.evaluate(
        "document.body.style.getPropertyValue('--vv-height').trim()"
    )
    assert vv, "--vv-height CSS property should be set after viewport resize"
    assert "px" in vv, f"--vv-height should be in pixels, got: {vv}"

    _close_keyboard(page)
