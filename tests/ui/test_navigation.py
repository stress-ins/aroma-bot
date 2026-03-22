"""Navigation: tabs, modes, back, section memory."""
from __future__ import annotations


def test_mobile_tabs_and_drafts_render_in_russian(page):
    sub_tabs = page.locator(".content-sub-tab").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "Планы" in sub_tabs
    assert "Публикации" in sub_tabs
    assert "Упоминания" in sub_tabs
    assert "Архив" in sub_tabs

    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(100)

    tabs_handbook = page.locator(".tab-button").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "🌿Ароматы" in tabs_handbook
    assert "🧭Теория" in tabs_handbook
    assert "🫁Практики" in tabs_handbook
    assert "🔔Звуки" in tabs_handbook

    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    page.evaluate("window.goBackToList()")

    page.locator(".draft-card").first.wait_for(state="visible")
    assert page.locator(".draft-card").count() >= 2
    assert not page.locator("#emptyState").is_visible()


def test_mobile_bottom_tab_bar_switches_primary_sections(page):
    bottom_nav = page.locator("#bottomTabBar")
    assert bottom_nav.is_visible()

    # Navigate to "Контент" bottom tab which shows plans
    page.locator("#btnTabContent").click()
    page.wait_for_timeout(100)
    assert page.locator("#btnTabContent").get_attribute("aria-pressed") == "true"
    assert page.locator(".plans-calendar-strip").is_visible()

    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(100)
    assert page.locator("#btnTabHandbook").get_attribute("aria-pressed") == "true"
    handbook_tabs = page.locator(".tab-button").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "🌿Ароматы" in handbook_tabs
    assert "🫁Практики" in handbook_tabs
    assert "🔔Звуки" in handbook_tabs

    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    assert page.locator("#btnTabInspiration").get_attribute("aria-pressed") == "true"
    # Inspiration shows drafts (Черновики) by default
    page.wait_for_timeout(100)
    assert page.locator(".draft-card").count() >= 2


def test_mobile_handbook_tab_remembers_last_section(page):
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(100)
    page.get_by_role("button", name="Практики").click()
    page.wait_for_timeout(100)

    active_before = page.locator(".tab-button.active").inner_text().strip()
    assert "Практики" in active_before

    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(100)

    active_after = page.locator(".tab-button.active").inner_text().strip()
    assert "Практики" in active_after


def test_overview_lists_use_consistent_card_meta(page):
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    assert page.locator(".draft-card .overview-card-date").first.inner_text().strip()

    # Switch to Контент tab, then check plans sub-tab
    page.locator("#btnTabContent").click()
    page.wait_for_timeout(100)
    page.locator(".content-sub-tab", has_text="Планы").click()
    page.wait_for_timeout(100)
    assert page.locator(".plan-card .draft-kind").first.is_visible()
    assert page.locator(".plan-card .overview-card-date").first.is_visible()

    page.locator(".content-sub-tab", has_text="Публикации").click()
    page.wait_for_timeout(100)
    page.get_by_text("Вечерний ароматический ритуал").first.click()
    page.wait_for_timeout(100)
    assert page.locator(".reels-frame-v2").count() >= 1


def test_desktop_layout_keeps_split_panels_and_comfortable_controls(desktop_page):
    desktop_page.evaluate("document.getElementById('btnTabContent')?.click()")
    desktop_page.wait_for_timeout(100)
    desktop_page.wait_for_selector(".content-sub-tab", timeout=10000)
    desktop_page.locator(".content-sub-tab", has_text="Публикации").click()
    desktop_page.wait_for_timeout(100)
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


def test_mobile_swipe_back_from_left_edge_works_over_interactive_controls(page):
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(100)
    page.get_by_text("Сенсорная карусель для вечернего ритуала").first.click()
    page.wait_for_timeout(100)

    page.evaluate(
        """
        () => {
          const button = document.querySelector('#draftDetail .prompt-actions .secondary-button');
          if (!button) throw new Error('detail action button not found');
          const makeEvent = (type, touches, changedTouches = touches) => {
            const event = new Event(type, { bubbles: true, cancelable: true });
            Object.defineProperty(event, 'touches', { value: touches });
            Object.defineProperty(event, 'changedTouches', { value: changedTouches });
            return event;
          };
          const start = [{ clientX: 12, clientY: 180 }];
          const move = [{ clientX: 120, clientY: 184 }];
          button.dispatchEvent(makeEvent('touchstart', start));
          button.dispatchEvent(makeEvent('touchmove', move));
          button.dispatchEvent(makeEvent('touchend', [], move));
        }
        """
    )
    # animateBackToList uses setTimeout(180ms) — wait for animation to complete
    page.wait_for_timeout(400)

    assert page.locator("#listPanel").evaluate("(node) => !node.classList.contains('hidden-mobile')")
    assert page.locator("#detailPanel").evaluate("(node) => node.classList.contains('hidden-mobile')")
    assert page.get_by_text("Сенсорная карусель для вечернего ритуала").first.is_visible()


def test_themed_tabs_and_drafts_render(themed_page):
    """Tab labels and draft cards render correctly in both themes."""
    # Inspiration tab shows Черновики / Тренды sub-tabs
    themed_page.locator("#btnTabInspiration").click()
    themed_page.wait_for_timeout(100)
    sub_tabs = themed_page.locator(".content-sub-tab").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert "Черновики" in sub_tabs
    assert "Тренды" in sub_tabs
    assert themed_page.locator(".draft-card").count() >= 2


def test_themed_bottom_tab_bar_switches_sections(themed_page):
    """Bottom tab navigation works in both themes."""
    themed_page.locator("#btnTabContent").click()
    themed_page.wait_for_timeout(100)
    assert themed_page.locator("#btnTabContent").get_attribute("aria-pressed") == "true"

    themed_page.locator("#btnTabHandbook").click()
    themed_page.wait_for_timeout(100)
    assert themed_page.locator("#btnTabHandbook").get_attribute("aria-pressed") == "true"

    themed_page.locator("#btnTabInspiration").click()
    themed_page.wait_for_timeout(100)
    assert themed_page.locator("#btnTabInspiration").get_attribute("aria-pressed") == "true"
