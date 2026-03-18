"""Reels preview modal: overlay text, close button, TG zone safety."""
from __future__ import annotations

import json

from .helpers import DOM_RENDER


def test_reels_preview_modal_opens_with_overlay_text(page):
    """openReelsPreview() opens the preview modal with overlay text."""
    page.evaluate("""() => {
        window.openReelsPreview('/generated/reels_assets/reels001/frame_1.png', 'Попробуй сегодня', 'f1', 'd1');
    }""")
    page.wait_for_timeout(DOM_RENDER)

    modal = page.locator("#reels-img-modal")
    assert modal.is_visible()
    assert page.locator(".preview-modal-header h3").inner_text() == "Предпросмотр"
    overlay = page.locator(".reels-overlay-text")
    assert overlay.is_visible()
    assert "Попробуй сегодня" in overlay.inner_text()


def test_reels_preview_modal_close_button(page):
    """X button closes the preview modal."""
    page.evaluate("""() => {
        window.openReelsPreview('/generated/reels_assets/reels001/frame_1.png', 'Test', 'f1', 'd1');
    }""")
    page.wait_for_timeout(DOM_RENDER)

    assert page.locator("#reels-img-modal").is_visible()
    page.locator("#reels-preview-close").click()
    page.wait_for_timeout(DOM_RENDER)
    assert not page.locator("#reels-img-modal").is_visible()


def test_reels_preview_close_button_not_in_tg_zone(page):
    """Close button uses safe-area padding, within the header bounds."""
    page.evaluate("""() => {
        window.openReelsPreview('/generated/reels_assets/reels001/frame_1.png', 'Test overlay', 'f1', 'd1');
    }""")
    page.wait_for_timeout(DOM_RENDER)

    header = page.locator(".preview-modal-header")
    assert header.is_visible()

    close_btn = page.locator("#reels-preview-close")
    assert close_btn.is_visible()

    header_box = header.bounding_box()
    close_box = close_btn.bounding_box()
    assert close_box is not None
    assert header_box is not None
    # Close button should be within the header bounds
    assert close_box["y"] >= header_box["y"]
    assert close_box["y"] + close_box["height"] <= header_box["y"] + header_box["height"] + 2


def test_reels_preview_without_overlay_shows_plain_image(page):
    """openReelsPreview with empty overlay text shows image without overlay div."""
    page.evaluate("""() => {
        window.openReelsPreview('/generated/reels_assets/reels001/frame_1.png', '', '', '');
    }""")
    page.wait_for_timeout(DOM_RENDER)

    assert page.locator("#reels-img-modal").is_visible()
    assert page.locator(".preview-modal-body img").is_visible()
    assert not page.locator(".reels-overlay-text").is_visible()
