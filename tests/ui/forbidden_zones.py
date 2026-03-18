"""Forbidden zones for Telegram Mini App UI tests.

Telegram on iOS/Android overlays native UI elements (header buttons, Dynamic Island,
Home Indicator) on specific screen areas. Interactive app elements must not overlap
these zones.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Tunable constants ---
TG_HEADER_HEIGHT = 55
TG_HEADER_BUTTON_WIDTH = 90
DYNAMIC_ISLAND_HALF_W = 65
DYNAMIC_ISLAND_H = 36
HOME_INDICATOR_H = 34


@dataclass(frozen=True)
class ForbiddenZone:
    """A rectangular screen area where interactive elements must not be placed."""

    name: str
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


def get_forbidden_zones(viewport_w: int, viewport_h: int) -> list[ForbiddenZone]:
    """Return forbidden zones for the given viewport dimensions."""
    return [
        # Telegram header — back button (top-left)
        ForbiddenZone(
            name="tg_header_back",
            x=0,
            y=0,
            width=TG_HEADER_BUTTON_WIDTH,
            height=TG_HEADER_HEIGHT,
        ),
        # Telegram header — kebab/more button (top-right)
        ForbiddenZone(
            name="tg_header_more",
            x=viewport_w - TG_HEADER_BUTTON_WIDTH,
            y=0,
            width=TG_HEADER_BUTTON_WIDTH,
            height=TG_HEADER_HEIGHT,
        ),
        # Dynamic Island (top-center, iOS 14 Pro+)
        ForbiddenZone(
            name="dynamic_island",
            x=(viewport_w / 2) - DYNAMIC_ISLAND_HALF_W,
            y=0,
            width=DYNAMIC_ISLAND_HALF_W * 2,
            height=DYNAMIC_ISLAND_H,
        ),
        # Home Indicator (bottom strip)
        ForbiddenZone(
            name="home_indicator",
            x=0,
            y=viewport_h - HOME_INDICATOR_H,
            width=viewport_w,
            height=HOME_INDICATOR_H,
        ),
    ]


def overlaps(element_box: dict, zone: ForbiddenZone) -> bool:
    """Check if an element's bounding box overlaps with a forbidden zone.

    element_box has keys: x, y, width, height (as returned by Playwright's bounding_box()).
    """
    ex, ey = element_box["x"], element_box["y"]
    ew, eh = element_box["width"], element_box["height"]

    # No overlap if one rect is entirely to the side/above/below the other
    if ex + ew <= zone.x:
        return False
    if ex >= zone.right:
        return False
    if ey + eh <= zone.y:
        return False
    if ey >= zone.bottom:
        return False
    return True


# Selectors for interactive elements that must not overlap forbidden zones
INTERACTIVE_SELECTORS = [
    "button",
    "a[href]",
    "input",
    "select",
    "textarea",
    "[role='button']",
    "[role='link']",
    "[role='tab']",
    "[onclick]",
    "[tabindex]:not([tabindex='-1'])",
]
