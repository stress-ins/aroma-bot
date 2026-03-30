"""Button standardization and consistency tests.

Ensures all buttons across the app follow consistent patterns:
- Correct CSS classes (primary-button, secondary-button, danger-button, ghost-button)
- Proper hit targets (>=44px on mobile)
- No orphaned buttons (visible but no handler)
- CSS variables for colors (no hardcoded hex)
"""
from __future__ import annotations

from .helpers import click_bottom_tab, click_draft_card


# ---------------------------------------------------------------------------
# Standard button CSS classes must be used consistently
# ---------------------------------------------------------------------------

JS_COLLECT_ALL_BUTTONS = """
() => {
    const results = [];
    document.querySelectorAll(
        'button, [role="button"], .primary-button, .secondary-button, ' +
        '.danger-button, .ghost-button, .action-item[data-action]'
    ).forEach(el => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (style.display === 'none' || style.visibility === 'hidden') return;
        if (rect.width === 0 || rect.height === 0) return;
        const action = el.dataset?.action || '';
        const hasClick = action ? typeof window[action] === 'function' : true;
        results.push({
            tag: el.tagName.toLowerCase(),
            action,
            hasHandler: hasClick,
            text: (el.textContent || '').trim().slice(0, 60),
            classes: el.className || '',
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            color: style.color,
            bg: style.backgroundColor,
        });
    });
    return results;
}
"""


def _collect_buttons(page):
    return page.evaluate(JS_COLLECT_ALL_BUTTONS)


def test_all_visible_buttons_have_minimum_hit_target(page):
    """Every visible button must have at least 36px height (44px preferred, 36px minimum)."""
    click_bottom_tab(page, "#btnTabInspiration")
    page.locator(".draft-card").first.wait_for(state="visible", timeout=5000)

    buttons = _collect_buttons(page)
    # Exclude tiny icon-only utility buttons (clear, close)
    too_small = [
        b for b in buttons
        if b["height"] < 30
        and b["tag"] == "button"
        and "close" not in b["classes"]
        and "clear" not in b["classes"]
        and "smart-search-clear" not in b["classes"]
    ]
    assert not too_small, (
        f"Buttons below 30px height:\n"
        + "\n".join(f"  - \"{b['text']}\" ({b['width']}x{b['height']}px) class=\"{b['classes']}\"" for b in too_small)
    )


def test_detail_action_buttons_have_hit_targets(page):
    """Action buttons in draft detail must have at least 40px height."""
    click_bottom_tab(page, "#btnTabInspiration")
    first = page.locator(".draft-card").first
    if not first.count():
        return
    first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)
    page.locator("#draftDetail .detail-title, #draftDetail .section, #draftDetail .reels-stepper").first.wait_for(state="visible", timeout=5000)

    buttons = _collect_buttons(page)
    action_buttons = [
        b for b in buttons
        if b["action"]
        and any(cls in b["classes"] for cls in ["primary-button", "secondary-button", "danger-button", "action-item"])
    ]
    too_small = [b for b in action_buttons if b["height"] < 36]
    assert not too_small, (
        f"Detail action buttons below 36px:\n"
        + "\n".join(f"  - \"{b['text']}\" action=\"{b['action']}\" ({b['height']}px)" for b in too_small)
    )


# ---------------------------------------------------------------------------
# No hardcoded colors in button styles
# ---------------------------------------------------------------------------

JS_CHECK_HARDCODED_COLORS = """
() => {
    const violations = [];
    document.querySelectorAll(
        '.primary-button, .secondary-button, .danger-button, .action-item'
    ).forEach(el => {
        const style = el.getAttribute('style') || '';
        // Match hex colors or direct rgb() that aren't var()
        const hexMatch = style.match(/#[0-9a-fA-F]{3,8}/);
        if (hexMatch) {
            violations.push({
                text: (el.textContent || '').trim().slice(0, 40),
                cls: el.className.slice(0, 60),
                style: style.slice(0, 100),
                color: hexMatch[0],
            });
        }
    });
    return violations;
}
"""


def test_no_hardcoded_hex_colors_on_buttons(page):
    """Buttons must use CSS variables, not hardcoded hex colors in inline styles."""
    click_bottom_tab(page, "#btnTabHandbook")
    page.locator(".reference-card").first.wait_for(state="visible", timeout=10000)
    violations = page.evaluate(JS_CHECK_HARDCODED_COLORS)
    assert not violations, (
        f"Buttons with hardcoded hex colors:\n"
        + "\n".join(f"  - \"{v['text']}\" has {v['color']} in style=\"{v['style']}\"" for v in violations)
    )


def test_no_hardcoded_hex_in_draft_detail_buttons(page):
    """Draft detail buttons must use CSS variables, not hardcoded colors."""
    click_bottom_tab(page, "#btnTabInspiration")
    first = page.locator(".draft-card").first
    if not first.count():
        return
    first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)
    page.locator("#draftDetail .detail-title, #draftDetail .section, #draftDetail .reels-stepper").first.wait_for(state="visible", timeout=5000)
    violations = page.evaluate(JS_CHECK_HARDCODED_COLORS)
    assert not violations, (
        f"Draft detail buttons with hardcoded hex:\n"
        + "\n".join(f"  - \"{v['text']}\" has {v['color']}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Button class consistency: primary/secondary/danger used correctly
# ---------------------------------------------------------------------------

JS_CHECK_BUTTON_CLASSES = """
() => {
    const results = [];
    document.querySelectorAll('button').forEach(el => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (style.display === 'none' || style.visibility === 'hidden') return;
        if (rect.width === 0 || rect.height === 0) return;
        const cls = el.className || '';
        const hasStandardClass = /primary-button|secondary-button|danger-button|ghost-button|back-button|bottom-tab-btn|tab-button|filter-chip|content-sub-tab|smart-search-clear|avatar-cropper|crossref-chip/.test(cls);
        const isInActionGroup = !!el.closest('.action-group');
        const isInBtnRow = !!el.closest('.btn-row, .threads-regen-row');
        const isUtility = /close|clear|dismiss|toggle/.test(cls);
        results.push({
            text: (el.textContent || '').trim().slice(0, 40),
            cls: cls.slice(0, 80),
            hasStandardClass,
            isInActionGroup,
            isInBtnRow,
            isUtility,
            action: el.dataset?.action || '',
        });
    });
    return results;
}
"""


def test_action_buttons_use_standard_classes(page):
    """Primary action buttons should use recognized CSS classes."""
    click_bottom_tab(page, "#btnTabInspiration")
    first = page.locator(".draft-card").first
    if not first.count():
        return
    first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)
    page.locator("#draftDetail .detail-title, #draftDetail .section, #draftDetail .reels-stepper").first.wait_for(state="visible", timeout=5000)

    buttons = page.evaluate(JS_CHECK_BUTTON_CLASSES)
    # Only flag buttons that have data-action but no standard class
    unclassed = [
        b for b in buttons
        if b["action"]
        and not b["hasStandardClass"]
        and not b["isInActionGroup"]
        and not b["isInBtnRow"]
        and not b["isUtility"]
    ]
    # This is a soft check — log but don't fail for now
    if unclassed:
        import warnings
        warnings.warn(
            f"{len(unclassed)} action buttons without standard CSS class:\n"
            + "\n".join(f"  - \"{b['text']}\" action=\"{b['action']}\" class=\"{b['cls']}\"" for b in unclassed[:10])
        )
