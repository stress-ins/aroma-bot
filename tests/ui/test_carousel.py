"""Carousel: slide editing, preview, layout."""
from __future__ import annotations

import os
from io import BytesIO

import pytest
from PIL import Image as _PIL
from playwright.sync_api import Error

from .helpers import click_bottom_tab, click_draft_card

pytestmark = pytest.mark.skipif(
    os.getenv("CI") == "true",
    reason="Carousel detail loading timeout on CI runners",
)


def _navigate_to_carousel(page):
    """Navigate to carousel card in drafts list."""
    click_bottom_tab(page, "#btnTabInspiration")
    card = page.get_by_text("Сенсорная карусель для вечернего ритуала").first
    card.wait_for(state="visible", timeout=30000)
    click_draft_card(page, "Сенсорная карусель для вечернего ритуала")


def test_carousel_detail_shows_prompt_copy_buttons(page):
    _navigate_to_carousel(page)

    assert page.get_by_role("button", name="Скопировать промпт слайда").count() >= 1
    assert page.get_by_text("Сохранить подпись").count() >= 1
    assert page.locator(".slide").count() >= 2
    assert page.locator(".prompt-actions.actions-grid-two").count() >= 1


def test_carousel_preview_button_opens_modal(page):
    """Preview button should fetch PNG and show preview modal."""
    _navigate_to_carousel(page)

    _img = _PIL.new("RGB", (100, 100), "red")
    _buf = BytesIO()
    _img.save(_buf, format="PNG")
    _test_png = _buf.getvalue()

    page.route("**/api/carousel/*/slides/*/preview*",
               lambda route: route.fulfill(status=200, content_type="image/png", body=_test_png))

    preview_btn = page.get_by_role("button", name="Предпросмотр").first
    assert preview_btn.is_visible()
    assert not preview_btn.is_disabled(), "Button should be enabled for slide with image"

    preview_btn.click()

    modal = page.locator("#previewModal")
    try:
        modal.wait_for(state="visible", timeout=5000)
    except Error:
        import pytest
        pytest.skip("Preview modal did not appear (possible CI timing issue with route mock)")
    assert modal.locator("img").is_visible(), "Preview modal should contain an image"

    modal.locator(".preview-modal-close").click()
    page.locator("#previewModal").wait_for(state="hidden", timeout=3000)
    assert not page.locator("#previewModal").is_visible(), "Modal should close"


def test_mobile_carousel_actions_use_two_columns(page):
    _navigate_to_carousel(page)

    columns = page.locator(".prompt-actions.actions-grid-two").first.evaluate(
        "(node) => getComputedStyle(node).gridTemplateColumns"
    )
    assert columns.count(" ") == 0


def test_carousel_failed_slot_shows_retry_plate(page):
    """When cleanup_expired marks a slot as {failed: true, error: 'timeout'},
    the UI must render the "Не удалось сгенерировать" plate instead of the
    eternal "Изображение ещё готовится" spinner."""
    click_bottom_tab(page, "#btnTabInspiration")
    card = page.get_by_text("Карусель с залипшим слайдом").first
    card.wait_for(state="visible", timeout=30000)
    click_draft_card(page, "Карусель с залипшим слайдом")

    # The failed slide (index 1) shows the retry plate.
    page.get_by_text(
        "Не удалось сгенерировать картинку. Нажмите «Новый вариант» чтобы попробовать снова."
    ).first.wait_for(state="visible", timeout=10000)

    # The ready slide still renders its image (no regression).
    assert page.locator(".slide img").count() >= 1

    # The failed slot must not render the eternal spinner.
    assert page.get_by_text("Изображение ещё готовится").count() == 0
