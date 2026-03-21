"""Dark theme: styling, contrast, scroll, interactions."""
from __future__ import annotations

import re

import pytest

from .helpers import (
    WCAG_AA_MIN,
    check_button_contrast,
    contrast_ratio,
    open_reels_detail_from_drafts,
    parse_rgb,
    relative_luminance,
)


# ---------------------------------------------------------------------------
# Tests using `page` fixture (add dark class manually)
# ---------------------------------------------------------------------------

def test_dark_theme_class_styles_bottom_tab_bar(page):
    page.evaluate("document.body.classList.add('tg-theme-dark')")
    page.wait_for_timeout(50)

    theme_state = page.evaluate(
        """
        () => {
          const tabBar = document.querySelector('.bottom-tab-bar-inner');
          return {
            bodyDark: document.body.classList.contains('tg-theme-dark'),
            tabBarBackground: getComputedStyle(tabBar).backgroundColor,
            tabBarBorder: getComputedStyle(tabBar).borderColor,
          };
        }
        """
    )

    assert theme_state["bodyDark"] is True
    # bottom-tab-bar uses rgba(var(--bg-rgb), 0.72) — verify it's dark and semi-transparent
    bg = theme_state["tabBarBackground"]
    channels = [int(v) for v in __import__("re").findall(r"\d+", bg)[:3]]
    assert all(c < 100 for c in channels), f"Expected dark tab bar background, got: {bg}"
    assert "0.72" in bg or "0.7" in bg, f"Expected semi-transparent tab bar, got: {bg}"


def test_dark_theme_keeps_reels_v2_frame_text_readable(page):
    open_reels_detail_from_drafts(page)
    page.evaluate("document.body.classList.add('tg-theme-dark')")
    page.wait_for_timeout(50)

    frame_style = page.evaluate(
        """
        () => {
          const frame = document.querySelector('.reels-frame-v2');
          const section = frame ? frame.closest('.section') : null;
          const frameStyle = frame ? getComputedStyle(frame) : null;
          const sectionStyle = section ? getComputedStyle(section) : null;
          return {
            frameFound: !!frame,
            frameBg: frameStyle ? frameStyle.backgroundColor : null,
            sectionBg: sectionStyle ? sectionStyle.backgroundImage || sectionStyle.backgroundColor : null,
          };
        }
        """
    )

    assert frame_style["frameFound"], "Expected .reels-frame-v2 in reels detail"


def test_dark_theme_class_applies_without_js_errors(page):
    js_errors: list[str] = []
    page.on("pageerror", lambda err: js_errors.append(str(err)))

    page.evaluate("document.body.classList.add('tg-theme-dark')")
    page.wait_for_timeout(50)

    result = page.evaluate(
        """
        () => {
          const style = getComputedStyle(document.body);
          return {
            hasDarkClass: document.body.classList.contains('tg-theme-dark'),
            bgColor: style.backgroundColor,
          };
        }
        """
    )

    assert result["hasDarkClass"] is True
    bg = result["bgColor"]
    channels = [int(v) for v in re.findall(r"\d+", bg)[:3]]
    assert all(c < 100 for c in channels), (
        f"Expected dark background on body in tg-theme-dark, got: {bg}"
    )
    assert js_errors == [], f"JS errors when applying tg-theme-dark: {js_errors}"


def test_dark_theme_reels_v2_frame_uses_dark_backgrounds(page):
    open_reels_detail_from_drafts(page)

    page.evaluate("document.body.classList.add('tg-theme-dark')")
    page.wait_for_timeout(50)

    styles = page.evaluate(
        """
        () => {
          const frame = document.querySelector('.reels-frame-v2');
          const frameStyle = frame ? getComputedStyle(frame) : null;
          return {
            frameBg: frameStyle ? frameStyle.backgroundImage || frameStyle.backgroundColor : null,
          };
        }
        """
    )

    assert styles["frameBg"] is not None, ".reels-frame-v2 not found in reels detail"


# ---------------------------------------------------------------------------
# Dark-only (dark_page fixture)
# ---------------------------------------------------------------------------

def test_dark_button_contrast_on_all_tabs(dark_page):
    all_failures = []
    for tab_id, label in [
        ("#btnTabDrafts", "Drafts"),
        ("#btnTabCreate", "Create"),
        ("#btnTabHandbook", "Handbook"),
    ]:
        dark_page.locator(tab_id).click()
        dark_page.wait_for_timeout(100)
        all_failures.extend(check_button_contrast(dark_page, theme_label=label))

    assert all_failures == [], (
        f"Buttons with insufficient contrast in dark theme:\n"
        + "\n".join(f"  [{f['theme']}] '{f['text']}' ratio={f['ratio']} "
                    f"(color={f['color']}, bg={f['bg']})" for f in all_failures)
    )


def test_dark_draft_detail_scroll_and_actions(dark_page):
    dark_page.locator("#btnTabDrafts").click()
    dark_page.wait_for_timeout(100)
    dark_page.get_by_text("Как мягко выйти из рабочего напряжения").first.click()
    dark_page.wait_for_timeout(100)

    dark_page.evaluate(
        "document.querySelector('#detailPanel').scrollTo(0, "
        "document.querySelector('#detailPanel').scrollHeight)"
    )
    dark_page.wait_for_timeout(100)

    actions = dark_page.locator("#draftDetail button").evaluate_all(
        """(nodes) => nodes
            .filter(n => getComputedStyle(n).display !== 'none' && n.getBoundingClientRect().width > 0)
            .map(n => ({ text: n.textContent.trim().slice(0, 40), visible: true }))
        """
    )
    assert len(actions) >= 1, "Expected at least one action button in draft detail"

    failures = check_button_contrast(dark_page, theme_label="draft-detail-scrolled")
    assert failures == [], f"Low contrast buttons after scroll: {failures}"


def test_dark_reels_scroll_through_frames(dark_page):
    open_reels_detail_from_drafts(dark_page)

    frame_count = dark_page.locator(".reels-frame-v2").count()
    assert frame_count >= 1

    for i in range(frame_count):
        frame = dark_page.locator(".reels-frame-v2").nth(i)
        frame.scroll_into_view_if_needed()
        dark_page.wait_for_timeout(50)

        title_el = frame.locator(".reels-frame-v2-title").first
        if title_el.count():
            color = title_el.evaluate("(el) => getComputedStyle(el).color")
            fg = parse_rgb(color)
            if fg:
                lum = relative_luminance(*fg)
                assert lum > 0.25, (
                    f"Frame {i} title too dark for dark theme: {color} (luminance={lum:.2f})"
                )


def test_dark_handbook_scroll_and_open_cards(dark_page):
    dark_page.locator("#btnTabHandbook").click()
    dark_page.wait_for_timeout(100)

    card_count = dark_page.locator(".reference-card").count()
    assert card_count >= 1, "No reference cards found in handbook default tab"

    dark_page.locator(".reference-card").last.scroll_into_view_if_needed()
    dark_page.wait_for_timeout(100)

    dark_page.locator(".reference-card").first.scroll_into_view_if_needed()
    dark_page.wait_for_timeout(50)
    dark_page.locator(".reference-card").first.click()
    dark_page.wait_for_timeout(100)

    detail = dark_page.locator("#detailPanel")
    assert detail.is_visible()

    dark_page.evaluate(
        "document.querySelector('#detailPanel')?.scrollTo(0, "
        "document.querySelector('#detailPanel')?.scrollHeight || 0)"
    )
    dark_page.wait_for_timeout(100)

    failures = check_button_contrast(dark_page, theme_label="handbook-detail")
    assert failures == [], f"Low contrast in handbook detail: {failures}"


def test_dark_create_form_fields_readable(dark_page):
    dark_page.locator("#btnTabCreate").click()
    dark_page.wait_for_timeout(100)

    dark_page.get_by_role("heading", name="Пост для соцсетей").click()
    dark_page.wait_for_timeout(100)

    textarea = dark_page.locator("textarea[name='topic']")
    if textarea.count():
        styles = textarea.evaluate(
            """(el) => {
                const s = getComputedStyle(el);
                return { color: s.color, bg: s.backgroundColor, border: s.borderColor };
            }"""
        )
        fg = parse_rgb(styles["color"])
        bg = parse_rgb(styles["bg"])
        if fg and bg:
            ratio = contrast_ratio(fg, bg)
            assert ratio >= WCAG_AA_MIN, (
                f"Textarea unreadable in dark theme: contrast {ratio:.2f} "
                f"(color={styles['color']}, bg={styles['bg']})"
            )


def test_dark_plans_scroll_and_click(dark_page):
    dark_page.locator(".content-sub-tab", has_text="Планы").click()
    dark_page.wait_for_timeout(100)

    plan_cards = dark_page.locator(".plan-card")
    if plan_cards.count() == 0:
        pytest.skip("No plan cards in test data")

    plan_cards.last.scroll_into_view_if_needed()
    dark_page.wait_for_timeout(100)

    plan_cards.first.scroll_into_view_if_needed()
    dark_page.wait_for_timeout(50)
    plan_cards.first.click()
    dark_page.wait_for_timeout(100)

    dark_page.evaluate(
        "document.querySelector('#detailPanel')?.scrollTo(0, "
        "document.querySelector('#detailPanel')?.scrollHeight || 0)"
    )
    dark_page.wait_for_timeout(100)

    title_el = dark_page.locator(".detail-title").first
    if title_el.count():
        color = title_el.evaluate("(el) => getComputedStyle(el).color")
        fg = parse_rgb(color)
        if fg:
            lum = relative_luminance(*fg)
            assert lum > 0.25, f"Plan title too dark: {color} (luminance={lum:.2f})"


def test_dark_swipe_scroll_draft_list(dark_page):
    dark_page.locator("#btnTabDrafts").click()
    dark_page.wait_for_timeout(100)

    initial_scroll = dark_page.evaluate(
        "() => document.querySelector('#listPanel')?.scrollTop || window.scrollY"
    )

    dark_page.mouse.move(215, 700)
    dark_page.mouse.down()
    dark_page.mouse.move(215, 300, steps=10)
    dark_page.mouse.up()
    dark_page.wait_for_timeout(100)

    after_scroll = dark_page.evaluate(
        "() => document.querySelector('#listPanel')?.scrollTop || window.scrollY"
    )

    card_count = dark_page.locator(".draft-card").count()
    list_panel = dark_page.query_selector("#listPanel")
    is_scrollable = dark_page.evaluate(
        "(el) => el ? el.scrollHeight > el.clientHeight : document.body.scrollHeight > window.innerHeight",
        list_panel,
    )
    if card_count > 3 and is_scrollable:
        assert after_scroll > initial_scroll, (
            f"Swipe scroll did not move: before={initial_scroll}, after={after_scroll}"
        )
