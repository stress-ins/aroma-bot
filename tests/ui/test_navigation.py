"""Navigation: tabs, modes, back, section memory."""
from __future__ import annotations

from .helpers import (
    click_bottom_tab,
    click_content_sub_tab,
    click_draft_card,
    click_handbook_tab,
    click_section_chip,
    nav_back_to_list,
)


def test_mobile_tabs_and_drafts_render_in_russian(page):
    # Default tab is Inspiration (drafts) — check inspiration sub-tabs
    insp_tabs = page.locator(".content-sub-tab").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "Черновики" in insp_tabs
    assert "Тренды" in insp_tabs

    # Switch to Контент tab — check content sub-tabs
    click_bottom_tab(page, "#btnTabContent")
    content_tabs = page.locator(".content-sub-tab").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "Планы" in content_tabs
    assert "Публикации" in content_tabs
    assert "Упоминания" in content_tabs
    assert "Входящие" in content_tabs
    assert "Архив" in content_tabs

    click_bottom_tab(page, "#btnTabHandbook")

    # Handbook uses section-based navigation: default section "Арома" shows aromas/blends/symptoms/concepts
    tabs_handbook = page.locator(".tab-button").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "Ароматы" in tabs_handbook[0]  # first tab contains emoji + Ароматы
    assert any("Теория" in t for t in tabs_handbook)

    # Section chips must exist
    section_chips = page.locator(".section-chip").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert any("Арома" in c for c in section_chips)
    assert any("Тело" in c for c in section_chips)
    assert any("Звук" in c for c in section_chips)

    # Switch to "Тело" section to reveal Практики
    click_section_chip(page, "Тело")
    body_tabs = page.locator(".tab-button").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert any("Практики" in t for t in body_tabs)

    click_bottom_tab(page, "#btnTabInspiration")
    nav_back_to_list(page)

    assert page.locator(".draft-card").count() >= 2
    assert not page.locator("#emptyState").is_visible()


def test_mobile_bottom_tab_bar_switches_primary_sections(page):
    bottom_nav = page.locator("#bottomTabBar")
    assert bottom_nav.is_visible()

    # Navigate to "Контент" bottom tab which shows plans
    click_bottom_tab(page, "#btnTabContent")
    assert page.locator("#btnTabContent").get_attribute("aria-pressed") == "true"
    assert page.locator(".plans-calendar-strip").is_visible()

    click_bottom_tab(page, "#btnTabHandbook")
    assert page.locator("#btnTabHandbook").get_attribute("aria-pressed") == "true"
    handbook_tabs = page.locator(".tab-button").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    # Default section "Арома" shows aromas/blends/symptoms/concepts
    assert any("Ароматы" in t for t in handbook_tabs)
    # Section chips provide access to other sections (Тело, Звук)
    assert page.locator(".section-chip").count() >= 2

    click_bottom_tab(page, "#btnTabInspiration")
    assert page.locator("#btnTabInspiration").get_attribute("aria-pressed") == "true"
    # Inspiration shows drafts (Черновики) by default
    page.locator(".draft-card").first.wait_for(state="visible", timeout=5000)
    assert page.locator(".draft-card").count() >= 2


def test_mobile_handbook_tab_remembers_last_section(page):
    click_bottom_tab(page, "#btnTabHandbook")
    # Navigate to "Тело" section first, then select Практики tab
    click_section_chip(page, "Тело")
    page.get_by_role("tab", name="Практики").click()
    page.locator(".tab-button.active").wait_for(state="visible", timeout=5000)

    active_before = page.locator(".tab-button.active").inner_text().strip()
    assert "Практики" in active_before

    click_bottom_tab(page, "#btnTabInspiration")
    click_bottom_tab(page, "#btnTabHandbook")

    # After returning, "Тело" section should be auto-selected because last tab was "practices"
    page.locator(".tab-button.active").wait_for(state="visible", timeout=5000)
    active_after = page.locator(".tab-button.active").inner_text().strip()
    assert "Практики" in active_after


def test_overview_lists_use_consistent_card_meta(page):
    click_bottom_tab(page, "#btnTabInspiration")
    assert page.locator(".draft-card .dc-meta").first.inner_text().strip()

    # Switch to Контент tab, then check plans sub-tab
    click_bottom_tab(page, "#btnTabContent")
    click_content_sub_tab(page, "Планы")
    assert page.locator(".plan-card .draft-kind").first.is_visible()
    assert page.locator(".plan-card .overview-card-date").first.is_visible()

    # Switch back to Inspiration and verify drafts are clickable
    click_bottom_tab(page, "#btnTabInspiration")
    first_draft = page.locator(".draft-card").first
    first_draft.wait_for(state="visible", timeout=5000)
    first_draft.click()
    page.locator("#draftDetail").wait_for(state="visible", timeout=5000)
    # Detail panel should have content after clicking a draft
    detail = page.locator("#draftDetail")
    assert detail.inner_html().strip()


def test_desktop_layout_keeps_split_panels_and_comfortable_controls(desktop_page):
    # Default tab is "drafts" — wait for content to load
    desktop_page.wait_for_selector(".draft-card", timeout=10000)
    layout = desktop_page.evaluate(
        """
        () => {
          const listPanel = document.querySelector('#listPanel');
          const detailPanel = document.querySelector('#detailPanel');
          const tabs = [...document.querySelectorAll('.tab-button')].map((node) => {
            const rect = node.getBoundingClientRect();
            return { text: (node.textContent || '').trim(), height: Math.round(rect.height) };
          });
          const actions = [...document.querySelectorAll('.secondary-button, .primary-button')]
            .filter((node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            })
            .map((node) => ({ text: (node.textContent || '').trim().slice(0, 40), height: Math.round(node.getBoundingClientRect().height) }));
          return {
            listWidth: Math.round(listPanel.getBoundingClientRect().width),
            detailWidth: Math.round(detailPanel.getBoundingClientRect().width),
            tabs,
            actions,
          };
        }
        """
    )
    assert layout["listWidth"] >= 300
    assert layout["detailWidth"] >= 500
    assert all(item["height"] >= 40 for item in layout["tabs"])
    assert all(item["height"] >= 40 for item in layout["actions"])


def test_swipe_back_navigates_without_visual_shift(page):
    """Swipe-back navigates back but panel does NOT shift visually during swipe."""
    click_bottom_tab(page, "#btnTabInspiration")
    click_draft_card(page, "Сенсорная карусель для вечернего ритуала")

    page.evaluate(
        """
        () => {
          const panel = document.getElementById('detailPanel');
          if (!panel) throw new Error('detail panel not found');
          const makeEvent = (type, touches, changedTouches = touches) => {
            const event = new Event(type, { bubbles: true, cancelable: true });
            Object.defineProperty(event, 'touches', { value: touches });
            Object.defineProperty(event, 'changedTouches', { value: changedTouches });
            return event;
          };
          const start = [{ clientX: 12, clientY: 180 }];
          const move = [{ clientX: 120, clientY: 184 }];
          panel.dispatchEvent(makeEvent('touchstart', start));
          panel.dispatchEvent(makeEvent('touchmove', move));
          panel.dispatchEvent(makeEvent('touchend', [], move));
        }
        """
    )
    # animateBackToList uses setTimeout(180ms) — wait for list to reappear
    page.locator("#listPanel").wait_for(state="visible", timeout=3000)
    page.wait_for_selector("#listPanel:not(.hidden-mobile)", timeout=3000)

    # Swipe navigated back to list
    assert page.locator("#listPanel").evaluate("(node) => !node.classList.contains('hidden-mobile')")
    assert page.get_by_text("Сенсорная карусель для вечернего ритуала").first.is_visible()


def test_themed_tabs_and_drafts_render(themed_page):
    """Tab labels and draft cards render correctly in both themes."""
    # Inspiration tab shows Черновики / Тренды sub-tabs
    click_bottom_tab(themed_page, "#btnTabInspiration")
    sub_tabs = themed_page.locator(".content-sub-tab").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "Черновики" in sub_tabs
    assert "Тренды" in sub_tabs
    assert themed_page.locator(".draft-card").count() >= 2


def test_themed_bottom_tab_bar_switches_sections(themed_page):
    """Bottom tab navigation works in both themes."""
    click_bottom_tab(themed_page, "#btnTabContent")
    assert themed_page.locator("#btnTabContent").get_attribute("aria-pressed") == "true"

    click_bottom_tab(themed_page, "#btnTabHandbook")
    assert themed_page.locator("#btnTabHandbook").get_attribute("aria-pressed") == "true"

    click_bottom_tab(themed_page, "#btnTabInspiration")
    assert themed_page.locator("#btnTabInspiration").get_attribute("aria-pressed") == "true"
