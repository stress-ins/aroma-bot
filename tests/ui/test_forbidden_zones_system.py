"""Tests for the forbidden zones system itself."""
from __future__ import annotations

import pytest

from tests.ui.forbidden_zones import (
    ForbiddenZone,
    get_forbidden_zones,
    overlaps,
)

# ---- Unit tests (no browser needed) ----


class TestZoneDefinitions:
    """Pure-logic tests for zone geometry."""

    def test_four_zones_for_mobile_viewport(self):
        zones = get_forbidden_zones(430, 932)
        assert len(zones) == 4
        names = {z.name for z in zones}
        assert names == {"tg_header_back", "tg_header_more", "dynamic_island", "home_indicator"}

    def test_safe_element_no_overlap(self):
        """An element in the centre of the screen should not overlap any zone."""
        zones = get_forbidden_zones(430, 932)
        box = {"x": 150, "y": 200, "width": 100, "height": 40}
        for zone in zones:
            assert not overlaps(box, zone), f"Unexpected overlap with {zone.name}"

    def test_element_in_header_overlaps(self):
        """An element at (0, 0) overlaps the header-back zone."""
        zones = get_forbidden_zones(430, 932)
        box = {"x": 0, "y": 0, "width": 50, "height": 30}
        back_zone = next(z for z in zones if z.name == "tg_header_back")
        assert overlaps(box, back_zone)

    def test_element_at_bottom_overlaps_home_indicator(self):
        zones = get_forbidden_zones(430, 932)
        box = {"x": 100, "y": 900, "width": 200, "height": 40}
        home_zone = next(z for z in zones if z.name == "home_indicator")
        assert overlaps(box, home_zone)

    def test_edge_touching_does_not_overlap(self):
        """An element whose edge exactly touches a zone boundary should NOT overlap."""
        zone = ForbiddenZone(name="test", x=0, y=0, width=90, height=55)
        # Element starts exactly at zone.right — no overlap
        box = {"x": 90, "y": 0, "width": 50, "height": 30}
        assert not overlaps(box, zone)
        # Element ends exactly at zone.y — no overlap
        box2 = {"x": 10, "y": -30, "width": 50, "height": 30}
        assert not overlaps(box2, zone)


# ---- Integration test (needs browser) ----


@pytest.mark.skip_zone_check
def test_catches_overlapping_button(page):
    """Inject a button into a forbidden zone and verify the check detects it."""
    from tests.ui.forbidden_zones import INTERACTIVE_SELECTORS, get_forbidden_zones

    page.evaluate("""() => {
        const btn = document.createElement('button');
        btn.textContent = 'BAD BUTTON';
        btn.id = 'bad-btn-test';
        btn.style.cssText = 'position:fixed;top:0;left:0;width:80px;height:40px;z-index:99999;';
        document.body.appendChild(btn);
    }""")

    vp = page.viewport_size
    zones = get_forbidden_zones(vp["width"], vp["height"])

    violations = []
    for selector in INTERACTIVE_SELECTORS:
        for el in page.locator(selector).all():
            box = el.bounding_box()
            if box is None or box["width"] == 0 or box["height"] == 0:
                continue
            for zone in zones:
                if overlaps(box, zone):
                    tag = el.evaluate("e => e.tagName.toLowerCase()")
                    text = (el.evaluate("e => (e.textContent || '').trim()") or "")[:40]
                    violations.append(f"<{tag}> '{text}' overlaps '{zone.name}'")

    assert any("bad-btn-test" in v or "BAD BUTTON" in v for v in violations), (
        f"Expected injected button to be caught. Violations: {violations}"
    )
