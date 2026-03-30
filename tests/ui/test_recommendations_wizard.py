"""Recommendations wizard: back navigation on mobile."""
from __future__ import annotations

from tests.ui.helpers import DOM_RENDER


def _open_wizard(page):
    """Open the recommendations wizard via JS bridge."""
    page.evaluate("window.openRecommendationsWizard()")
    page.locator(".reco-wizard").wait_for(state="visible", timeout=5000)


def test_wizard_back_from_step0_closes_wizard(page):
    """Back button at step 0 should close the wizard entirely."""
    _open_wizard(page)
    assert page.locator(".reco-wizard").is_visible()

    # Click the back button (should have data-action="closeRecommendationsWizard")
    page.locator(".back-button").click()
    page.wait_for_selector("#listPanel:not(.hidden-mobile)", timeout=5000)

    # Wizard should be closed, list view visible
    assert page.locator("#listPanel").evaluate("(el) => !el.classList.contains('hidden-mobile')")


def test_wizard_back_from_step1_goes_to_step0(page):
    """Back button at step 1 should go back to step 0, not close wizard."""
    _open_wizard(page)

    # Select mood to enable Next
    page.locator(".reco-chip").first.click()
    page.wait_for_timeout(DOM_RENDER)

    # Go to step 1
    page.locator("[data-action='recoWizardNext']").click()
    page.locator(".reco-step-title").wait_for(state="visible", timeout=5000)
    assert page.locator(".reco-step-title").inner_text() == "Что хотите получить?"

    # Click back
    page.locator(".back-button").click()
    page.locator(".reco-step-title").wait_for(state="visible", timeout=5000)

    # Should be back to step 0 (mood), wizard still open
    assert page.locator(".reco-wizard").is_visible()
    assert page.locator(".reco-step-title").inner_text() == "Как вы себя чувствуете?"


def test_wizard_goBackToList_respects_wizard_state(page):
    """goBackToList() (TG BackButton / swipe) at step 2 should go to step 1."""
    _open_wizard(page)

    # Step 0 -> select mood -> next
    page.locator(".reco-chip").first.click()
    page.wait_for_timeout(DOM_RENDER)
    page.locator("[data-action='recoWizardNext']").click()
    page.locator(".reco-step-title").wait_for(state="visible", timeout=5000)

    # Step 1 -> select goal -> next
    page.locator(".reco-chip").first.click()
    page.wait_for_timeout(DOM_RENDER)
    page.locator("[data-action='recoWizardNext']").click()
    page.locator(".reco-step-title").wait_for(state="visible", timeout=5000)

    # Now at step 2
    assert page.locator(".reco-step-title").inner_text() == "Есть ли симптомы?"

    # Simulate TG BackButton / swipe via goBackToList
    page.evaluate("window.goBackToList()")
    page.locator(".reco-step-title", has_text="Что хотите получить?").wait_for(state="visible", timeout=5000)

    # Should go back to step 1, not close wizard
    assert page.locator(".reco-wizard").is_visible()
    assert page.locator(".reco-step-title").inner_text() == "Что хотите получить?"


def test_wizard_goBackToList_at_step0_closes_wizard(page):
    """goBackToList() at step 0 should close the wizard."""
    _open_wizard(page)
    assert page.locator(".reco-wizard").is_visible()

    page.evaluate("window.goBackToList()")
    page.wait_for_selector("#listPanel:not(.hidden-mobile)", timeout=5000)

    # Wizard should be closed
    assert page.locator("#listPanel").evaluate("(el) => !el.classList.contains('hidden-mobile')")
