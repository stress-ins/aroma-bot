"""Visual debug utility — renders forbidden zones on a screenshot.

Run: pytest tests/ui/zone_debugger.py -v -s
"""
from __future__ import annotations

import pytest

from tests.ui.forbidden_zones import get_forbidden_zones

SCREENSHOT_DIR = "docs/screenshots"
SCREENSHOT_FILE = "forbidden_zones_debug.png"

ZONE_COLORS = {
    "tg_header_back": "rgba(255, 0, 0, 0.30)",
    "tg_header_more": "rgba(255, 0, 0, 0.30)",
    "dynamic_island": "rgba(255, 165, 0, 0.30)",
    "home_indicator": "rgba(0, 0, 255, 0.30)",
}


@pytest.mark.skip_zone_check
def test_debug_forbidden_zones(page):
    """Inject overlay divs for every forbidden zone and take a screenshot."""
    import os

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    vp = page.viewport_size
    zones = get_forbidden_zones(vp["width"], vp["height"])

    for zone in zones:
        color = ZONE_COLORS.get(zone.name, "rgba(255, 0, 0, 0.25)")
        page.evaluate(
            """([name, x, y, w, h, color]) => {
                const div = document.createElement('div');
                div.style.cssText = `
                    position: fixed; z-index: 99999; pointer-events: none;
                    left: ${x}px; top: ${y}px; width: ${w}px; height: ${h}px;
                    background: ${color};
                    border: 2px dashed red;
                    font: bold 11px/1 monospace; color: red;
                    display: flex; align-items: center; justify-content: center;
                `;
                div.textContent = name;
                document.body.appendChild(div);
            }""",
            [zone.name, zone.x, zone.y, zone.width, zone.height, color],
        )

    path = f"{SCREENSHOT_DIR}/{SCREENSHOT_FILE}"
    page.screenshot(path=path, full_page=False)
    print(f"\nForbidden-zones debug screenshot saved: {path}")
