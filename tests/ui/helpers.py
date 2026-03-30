"""Shared helper functions for UI tests."""
from __future__ import annotations

import os
import re
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

_SNAPSHOT_DIR = Path(__file__).with_name("snapshots")


# ---------------------------------------------------------------------------
# Named timeout constants (ms) — replace magic numbers in tests
# ---------------------------------------------------------------------------

DOM_RENDER = 100       # Minimal wait for DOM re-render after click/evaluate
ANIMATION = 300        # CSS transition / animation completion
API_ROUNDTRIP = 500    # Network request round-trip
THEME_APPLY = 50       # Dark/light theme class application


# ---------------------------------------------------------------------------
# Wait helpers — prefer these over page.wait_for_timeout(N)
# ---------------------------------------------------------------------------

def wait_visible(page, selector: str, *, timeout: int = 5000) -> None:
    """Wait until a selector is visible on the page."""
    page.locator(selector).first.wait_for(state="visible", timeout=timeout)


def wait_hidden(page, selector: str, *, timeout: int = 5000) -> None:
    """Wait until a selector is hidden/detached from the page."""
    page.locator(selector).first.wait_for(state="hidden", timeout=timeout)


def wait_for_app_ready(page, *, timeout: int = 10000) -> None:
    """Wait until body.app-ready appears (miniapp JS init complete)."""
    page.wait_for_selector("body.app-ready", timeout=timeout)


# ---------------------------------------------------------------------------
# Visual snapshot helpers
# ---------------------------------------------------------------------------

def prepare_visual_state(page) -> None:
    page.add_style_tag(
        content="""
        *,
        *::before,
        *::after {
          animation: none !important;
          transition: none !important;
          caret-color: transparent !important;
          scroll-behavior: auto !important;
        }
        """
    )
    page.wait_for_timeout(DOM_RENDER)


def assert_scroll_snapshots(
    page,
    snapshot_prefix: str,
    *,
    scroll_selector: str = "#detailPanel",
    max_diff_ratio: float = 0.0025,
) -> None:
    """Capture viewport-size scroll snapshots of a scrollable container.

    For long detail screens that exceed the viewport height.
    Produces: {prefix}_scroll_0.png, {prefix}_scroll_1.png, ...
    Always uses full_page=False — only the viewport is captured.
    """
    import math

    vp = page.viewport_size
    viewport_height = vp["height"] if vp else 852

    total_height = page.evaluate(
        f"document.querySelector('{scroll_selector}')?.scrollHeight || 0"
    )
    if total_height <= viewport_height:
        prepare_visual_state(page)
        assert_visual_snapshot(
            page.locator(scroll_selector), f"{snapshot_prefix}_scroll_0.png",
            max_diff_ratio=max_diff_ratio,
        )
        return

    num_frames = math.ceil(total_height / viewport_height)
    prepare_visual_state(page)

    for i in range(num_frames):
        page.evaluate(
            f"document.querySelector('{scroll_selector}').scrollTop = {i * viewport_height}"
        )
        page.wait_for_timeout(DOM_RENDER)
        assert_visual_snapshot(
            page.locator(".shell"), f"{snapshot_prefix}_scroll_{i}.png",
            max_diff_ratio=max_diff_ratio,
        )

    # Scroll back to top
    page.evaluate(f"document.querySelector('{scroll_selector}').scrollTop = 0")
    page.wait_for_timeout(DOM_RENDER)


def _save_visual_report(
    report_dir: str,
    snapshot_name: str,
    expected: "Image.Image",
    actual: "Image.Image",
    diff_mask: "np.ndarray",
    diff_ratio: float,
) -> None:
    """Save baseline/actual/diff/comparison images for CI reporting."""
    from PIL import ImageDraw

    out = Path(report_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(snapshot_name).stem

    expected.save(out / f"{stem}_baseline.png")
    actual.save(out / f"{stem}_actual.png")

    # Diff highlight: red overlay on changed pixels
    diff_highlight = actual.copy()
    px = np.array(diff_highlight)
    px[diff_mask] = [255, 0, 0, 255]
    diff_img = Image.fromarray(px)
    diff_img.save(out / f"{stem}_diff.png")

    # Side-by-side comparison
    w, h = actual.size
    gap = 10
    comp = Image.new("RGBA", (w * 3 + gap * 2, h + 25), (30, 30, 30, 255))
    comp.paste(expected, (0, 25))
    comp.paste(actual, (w + gap, 25))
    comp.paste(diff_img, (w * 2 + gap * 2, 25))

    draw = ImageDraw.Draw(comp)
    draw.text((w // 2 - 30, 5), "Baseline", fill=(200, 200, 200))
    draw.text((w + gap + w // 2 - 20, 5), "Actual", fill=(200, 200, 200))
    draw.text((w * 2 + gap * 2 + w // 2 - 40, 5), f"Diff ({diff_ratio:.2%})", fill=(255, 80, 80))
    comp.save(out / f"{stem}_comparison.png")


def assert_visual_snapshot(locator, snapshot_name: str, *, max_diff_ratio: float = 0.0025) -> None:
    expected_path = _SNAPSHOT_DIR / snapshot_name
    actual_bytes = locator.screenshot(animations="disabled")

    if os.getenv("UPDATE_VISUAL_BASELINE") == "1":
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        expected_path.write_bytes(actual_bytes)
        return

    assert expected_path.exists(), f"Missing visual baseline: {expected_path}"

    expected = Image.open(expected_path).convert("RGBA")
    actual = Image.open(BytesIO(actual_bytes)).convert("RGBA")

    w = min(actual.size[0], expected.size[0])
    h = min(actual.size[1], expected.size[1])
    expected = expected.crop((0, 0, w, h))
    actual = actual.crop((0, 0, w, h))

    expected_pixels = np.array(expected)
    actual_pixels = np.array(actual)
    diff_mask = np.any(np.abs(actual_pixels.astype(np.int16) - expected_pixels.astype(np.int16)) > 12, axis=2)
    diff_ratio = float(diff_mask.mean())

    # Save visual report artifacts for CI when diff exceeds threshold
    report_dir = os.getenv("VISUAL_REPORT_DIR")
    if report_dir and diff_ratio > max_diff_ratio:
        _save_visual_report(report_dir, snapshot_name, expected, actual, diff_mask, diff_ratio)

    assert diff_ratio <= max_diff_ratio, (
        f"Visual regression in {snapshot_name}: diff ratio {diff_ratio:.4%} exceeds {max_diff_ratio:.4%}"
    )


# ---------------------------------------------------------------------------
# Navigation helpers — deterministic waits (no arbitrary timeouts)
# ---------------------------------------------------------------------------

def click_bottom_tab(page, tab_id: str, *, timeout: int = 5000) -> None:
    """Click a bottom tab and wait until it becomes active (aria-pressed)."""
    page.locator(tab_id).click()
    page.locator(f'{tab_id}[aria-pressed="true"]').wait_for(state="attached", timeout=timeout)


def click_content_sub_tab(page, label: str, *, timeout: int = 5000) -> None:
    """Click a content sub-tab and wait for it to become active."""
    page.locator(".content-sub-tab", has_text=label).click()
    page.locator(".content-sub-tab.active", has_text=label).wait_for(state="visible", timeout=timeout)


def click_draft_card(page, text: str, *, timeout: int = 5000) -> None:
    """Click a draft card by text and wait for detail view to render."""
    page.get_by_text(text).first.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=timeout)
    # Wait for detail content to actually populate (e.g. detail-title appears)
    page.locator("#draftDetail .detail-title, #draftDetail .section, #draftDetail .reels-stepper").first.wait_for(
        state="visible", timeout=timeout,
    )


def click_handbook_tab(page, name: str, *, timeout: int = 10000) -> None:
    """Click a handbook tab and wait for reference cards to appear."""
    page.get_by_role("tab", name=name).click()
    page.locator(".reference-card").first.wait_for(state="visible", timeout=timeout)


def click_section_chip(page, label: str, *, timeout: int = 5000) -> None:
    """Click a handbook section chip and wait for tabs to update."""
    page.locator(".section-chip", has_text=label).click()
    page.locator(".tab-button").first.wait_for(state="visible", timeout=timeout)


def nav_back_to_list(page, *, timeout: int = 5000) -> None:
    """Go back to list view and wait for draft cards to appear."""
    page.evaluate("window.goBackToList()")
    page.locator(".draft-card").first.wait_for(state="visible", timeout=timeout)


def click_create_tool(page, heading: str, *, timeout: int = 5000) -> None:
    """Click a create tool card and wait for form to appear."""
    page.get_by_role("heading", name=heading).click()
    page.locator("[data-create-content], textarea[name='topic'], .reco-wizard").first.wait_for(
        state="visible", timeout=timeout,
    )


def open_reels_detail_from_drafts(page):
    click_bottom_tab(page, "#btnTabInspiration")
    click_draft_card(page, "Вечерний ароматический ритуал")


def wait_for_detail_panel(page, *, timeout: int = 5000) -> None:
    """Wait for detail panel to have content."""
    page.locator("#draftDetail .detail-title, #draftDetail .section, #draftDetail .reels-stepper").first.wait_for(
        state="visible", timeout=timeout,
    )


# ---------------------------------------------------------------------------
# WCAG contrast helpers
# ---------------------------------------------------------------------------

WCAG_AA_MIN = 3.0  # minimum contrast ratio for large text / UI components


def relative_luminance(r: float, g: float, b: float) -> float:
    """Compute relative luminance per WCAG 2.1 (sRGB values 0-255)."""
    def linearize(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(rgb1: tuple, rgb2: tuple) -> float:
    l1 = relative_luminance(*rgb1)
    l2 = relative_luminance(*rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def parse_rgba(css_color: str) -> tuple | None:
    """Parse 'rgb(r, g, b)' or 'rgba(r, g, b, a)' into (r, g, b, a) tuple."""
    m = re.match(r"rgba?\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\s*\)", css_color)
    if not m:
        return None
    a = float(m.group(4)) if m.group(4) is not None else 1.0
    return (float(m.group(1)), float(m.group(2)), float(m.group(3)), a)


def parse_rgb(css_color: str) -> tuple | None:
    """Parse into (r, g, b) tuple, discarding alpha."""
    rgba = parse_rgba(css_color)
    return (rgba[0], rgba[1], rgba[2]) if rgba else None


def composite_over(fg_rgba: tuple, bg_rgb: tuple) -> tuple:
    """Composite a semi-transparent foreground over an opaque background."""
    r, g, b, a = fg_rgba
    return (
        r * a + bg_rgb[0] * (1 - a),
        g * a + bg_rgb[1] * (1 - a),
        b * a + bg_rgb[2] * (1 - a),
    )


JS_COLLECT_BUTTON_COLORS = """
() => {
    function findOpaqueAncestorBg(el) {
        let node = el;
        while (node && node !== document.documentElement) {
            const bg = getComputedStyle(node).backgroundColor;
            const m = bg.match(/rgba?\\(\\s*([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?/);
            if (m) {
                const a = m[4] !== undefined ? parseFloat(m[4]) : 1.0;
                if (a >= 0.95) return bg;
            }
            node = node.parentElement;
        }
        return getComputedStyle(document.body).backgroundColor;
    }
    const results = [];
    document.querySelectorAll(
        'button, .secondary-button, .primary-button, .bottom-tab-btn, .tab-button, .back-button'
    ).forEach(el => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (style.display === 'none' || style.visibility === 'hidden' || rect.width === 0) return;
        results.push({
            text: (el.textContent || '').trim().slice(0, 40),
            color: style.color,
            bg: style.backgroundColor,
            parentBg: findOpaqueAncestorBg(el.parentElement),
            cls: el.className.slice(0, 60),
        });
    });
    return results;
}
"""


def check_button_contrast(page, *, theme_label: str = "") -> list:
    """Return list of buttons with contrast ratio below WCAG AA threshold."""
    buttons = page.evaluate(JS_COLLECT_BUTTON_COLORS)

    failures = []
    for btn in buttons:
        fg_rgba = parse_rgba(btn["color"])
        bg_rgba = parse_rgba(btn["bg"])
        if fg_rgba is None or bg_rgba is None:
            continue
        if bg_rgba[3] < 0.01:
            continue
        ancestor_bg = parse_rgb(btn.get("parentBg", "")) or (255, 255, 255)
        effective_bg = composite_over(bg_rgba, ancestor_bg) if bg_rgba[3] < 1.0 else (bg_rgba[0], bg_rgba[1], bg_rgba[2])
        effective_fg = composite_over(fg_rgba, effective_bg) if fg_rgba[3] < 1.0 else (fg_rgba[0], fg_rgba[1], fg_rgba[2])
        ratio = contrast_ratio(effective_fg, effective_bg)
        if ratio < WCAG_AA_MIN:
            failures.append({
                "text": btn["text"],
                "cls": btn["cls"],
                "color": btn["color"],
                "bg": btn["bg"],
                "ratio": round(ratio, 2),
                "theme": theme_label,
            })
    return failures
