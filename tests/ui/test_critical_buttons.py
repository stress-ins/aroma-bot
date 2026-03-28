"""Critical button presence and handler registration tests.

These tests prevent regressions where buttons disappear from the UI
or are rendered without working event handlers (dead buttons).

Every data-action button on the page MUST have a matching window function.
Every critical section MUST have its expected action buttons.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Generic: every data-action button must have a registered handler
# ---------------------------------------------------------------------------

JS_CHECK_DEAD_BUTTONS = """
() => {
    const results = [];
    document.querySelectorAll('[data-action]').forEach(el => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (style.display === 'none' || style.visibility === 'hidden') return;
        if (rect.width === 0 || rect.height === 0) return;
        const action = el.dataset.action;
        const handler = window[action];
        results.push({
            action,
            hasHandler: typeof handler === 'function',
            text: (el.textContent || '').trim().slice(0, 60),
            tag: el.tagName.toLowerCase(),
            visible: true,
        });
    });
    return results;
}
"""


def _assert_no_dead_buttons(page, context: str = ""):
    """Assert every visible data-action element has a window handler function."""
    buttons = page.evaluate(JS_CHECK_DEAD_BUTTONS)
    dead = [b for b in buttons if not b["hasHandler"]]
    assert not dead, (
        f"Dead buttons (no handler) {context}:\n"
        + "\n".join(f"  - data-action=\"{b['action']}\" text=\"{b['text']}\"" for b in dead)
    )
    return buttons


# ---------------------------------------------------------------------------
# References / Handbook: action-group buttons
# ---------------------------------------------------------------------------

REFERENCE_ACTION_GROUP_ACTIONS = [
    "openBlendConstructor",
    "openRecommendationsWizard",
    "openSavedBlends",
]

REFERENCE_ACTION_GROUP_LABELS = [
    "Создать смесь под задачу",
    "Подобрать масло",
    "Сохранённое",
]


def test_handbook_action_group_buttons_present(page):
    """Action-group buttons (blend constructor, wizard, saved) must be visible in handbook."""
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(300)

    for action in REFERENCE_ACTION_GROUP_ACTIONS:
        btn = page.locator(f'[data-action="{action}"]')
        assert btn.count() > 0, f"Action-group button data-action=\"{action}\" missing from handbook"
        assert btn.first.is_visible(), f"Action-group button data-action=\"{action}\" is hidden"

    for label in REFERENCE_ACTION_GROUP_LABELS:
        assert page.locator(".action-group").get_by_text(label).is_visible(), (
            f"Action-group label \"{label}\" not visible"
        )


def test_handbook_action_group_has_handlers(page):
    """Each action-group button must have a registered handler in window."""
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(300)

    _assert_no_dead_buttons(page, context="in handbook")


def test_handbook_action_group_survives_tab_switch(page):
    """Action-group must persist after switching tabs and returning (regression #870, #873)."""
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(300)

    # Verify initial state
    for action in REFERENCE_ACTION_GROUP_ACTIONS:
        assert page.locator(f'[data-action="{action}"]').is_visible()

    # Switch to another section and back
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(200)
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(300)

    # Buttons must still be there
    for action in REFERENCE_ACTION_GROUP_ACTIONS:
        btn = page.locator(f'[data-action="{action}"]')
        assert btn.count() > 0, f"Action-group button \"{action}\" disappeared after tab switch"
        assert btn.first.is_visible(), f"Action-group button \"{action}\" hidden after tab switch"


def test_handbook_action_group_survives_subtab_switch(page):
    """Action-group persists when switching between handbook sub-tabs."""
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(300)

    for action in REFERENCE_ACTION_GROUP_ACTIONS:
        assert page.locator(f'[data-action="{action}"]').is_visible()

    # Switch to a different sub-tab
    theory_tab = page.get_by_role("tab", name="Теория")
    if theory_tab.count():
        theory_tab.click()
        page.wait_for_timeout(300)

        for action in REFERENCE_ACTION_GROUP_ACTIONS:
            btn = page.locator(f'[data-action="{action}"]')
            assert btn.count() > 0, f"Action-group button \"{action}\" gone after sub-tab switch"
            assert btn.first.is_visible(), f"Action-group button \"{action}\" hidden after sub-tab switch"


# ---------------------------------------------------------------------------
# Drafts detail: action buttons per draft type
# ---------------------------------------------------------------------------

def test_threads_detail_has_action_buttons(page):
    """Threads draft detail must show save/polish/feedback action buttons."""
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(200)
    card = page.locator(".draft-card").filter(has_text="Как мягко выйти из рабочего напряжения").first
    if not card.count():
        return
    card.click()
    page.wait_for_timeout(400)

    # Must have at least save and polish buttons
    buttons = _assert_no_dead_buttons(page, context="in threads detail")
    action_names = [b["action"] for b in buttons]
    assert "saveContentReviewDraft" in action_names or "saveThreadsReviewDraft" in action_names, (
        f"No save button in threads detail. Actions found: {action_names}"
    )


def test_reels_detail_has_action_buttons(page):
    """Reels draft detail must show concept/scenario/caption action buttons."""
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(200)
    card = page.locator(".draft-card").filter(has_text="Вечерний ароматический ритуал").first
    if not card.count():
        return
    card.click()
    page.wait_for_timeout(400)

    buttons = _assert_no_dead_buttons(page, context="in reels detail")
    action_names = [b["action"] for b in buttons]
    # Reels must have at least approve or regenerate
    has_reels_action = any(
        a in action_names for a in ["approveReels", "regenConcept", "regenScenario", "jumpToReelsStep"]
    )
    assert has_reels_action, f"No reels actions in detail. Actions found: {action_names}"


def test_carousel_detail_has_action_buttons(page):
    """Carousel draft detail must show export/approve/regenerate action buttons."""
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(200)
    card = page.locator(".draft-card").filter(has_text="Сенсорная карусель для вечернего ритуала").first
    if not card.count():
        return
    card.click()
    page.wait_for_timeout(400)

    buttons = _assert_no_dead_buttons(page, context="in carousel detail")
    action_names = [b["action"] for b in buttons]
    has_carousel_action = any(
        a in action_names for a in [
            "downloadCarouselPptx", "exportToCanva", "updateDraft",
            "regenerateCarouselAll", "showCarouselPublishScreen",
        ]
    )
    assert has_carousel_action, f"No carousel actions in detail. Actions found: {action_names}"


def test_threads_series_detail_has_action_buttons(page):
    """Threads series detail must have approve/publish/regenerate buttons."""
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(200)
    card = page.locator(".draft-card").filter(has_text="Восстановление энергии").first
    if not card.count():
        return
    card.click()
    page.wait_for_timeout(400)

    buttons = _assert_no_dead_buttons(page, context="in threads series detail")
    action_names = [b["action"] for b in buttons]
    has_series_action = any(
        a in action_names for a in [
            "approveThreadsSeries", "publishThreadsSeriesNow",
            "regenerateSeriesPosts", "sendDraftToChat",
        ]
    )
    assert has_series_action, f"No series actions in detail. Actions found: {action_names}"


# ---------------------------------------------------------------------------
# Cross-section: no dead buttons anywhere
# ---------------------------------------------------------------------------

def test_no_dead_buttons_on_drafts_list(page):
    """Drafts list must not have any dead data-action buttons."""
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(300)
    _assert_no_dead_buttons(page, context="on drafts list")


def test_no_dead_buttons_on_plans(page):
    """Plans section must not have any dead data-action buttons."""
    page.locator("#btnTabContent").click()
    page.wait_for_timeout(200)
    page.locator(".content-sub-tab", has_text="Планы").click()
    page.wait_for_timeout(300)
    _assert_no_dead_buttons(page, context="on plans")


def test_no_dead_buttons_on_mentions(page):
    """Mentions section must not have any dead data-action buttons."""
    page.locator("#btnTabContent").click()
    page.wait_for_timeout(200)
    page.locator(".content-sub-tab", has_text="Упоминания").click()
    page.wait_for_timeout(300)
    _assert_no_dead_buttons(page, context="on mentions list")


def test_no_dead_buttons_on_archive(page):
    """Archive section must not have any dead data-action buttons."""
    page.locator("#btnTabContent").click()
    page.wait_for_timeout(200)
    page.locator(".content-sub-tab", has_text="Архив").click()
    page.wait_for_timeout(300)
    _assert_no_dead_buttons(page, context="on archive list")


# ---------------------------------------------------------------------------
# Dark theme: same checks
# ---------------------------------------------------------------------------

def test_handbook_action_group_buttons_present_dark(dark_page):
    """Action-group buttons must be visible in dark theme."""
    dark_page.locator("#btnTabHandbook").click()
    dark_page.wait_for_timeout(300)

    for action in REFERENCE_ACTION_GROUP_ACTIONS:
        btn = dark_page.locator(f'[data-action="{action}"]')
        assert btn.count() > 0, f"Action-group button \"{action}\" missing in dark theme"
        assert btn.first.is_visible(), f"Action-group button \"{action}\" hidden in dark theme"


def test_no_dead_buttons_on_handbook_dark(dark_page):
    """No dead buttons in handbook in dark theme."""
    dark_page.locator("#btnTabHandbook").click()
    dark_page.wait_for_timeout(300)
    _assert_no_dead_buttons(dark_page, context="in handbook (dark theme)")


# ---------------------------------------------------------------------------
# Console error detection: catch [data-action] errors from bridge.js
# ---------------------------------------------------------------------------

def test_no_data_action_console_errors_during_navigation(page):
    """Navigate through all sections and check no [data-action] errors appear."""
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if "[data-action]" in msg.text else None)

    # Navigate through main sections
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(200)
    page.locator("#btnTabContent").click()
    page.wait_for_timeout(200)
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(200)

    # Open a draft
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(200)
    first_card = page.locator(".draft-card").first
    if first_card.count():
        first_card.click()
        page.wait_for_timeout(300)

    assert not errors, (
        f"[data-action] console errors detected:\n" + "\n".join(f"  - {e}" for e in errors)
    )
