"""Button row layout: equal widths, vertical alignment, centered content."""
from __future__ import annotations


def _navigate_to_threads_detail(page):
    """Go to Drafts tab and open the threads_series draft to get .btn-row buttons."""
    page.locator("#btnTabInspiration").click()
    page.wait_for_timeout(300)
    card = page.locator(".draft-card").filter(has_text="Восстановление энергии").first
    if card.count():
        card.click()
        page.wait_for_timeout(400)
        return True
    return False


def test_btn_row_buttons_equal_width(page):
    """All buttons inside .btn-row should have equal width (±2px)."""
    if not _navigate_to_threads_detail(page):
        return

    rows = page.locator(".btn-row")
    count = rows.count()
    if count == 0:
        return

    for i in range(count):
        widths = rows.nth(i).evaluate(
            """row => [...row.querySelectorAll('button, .btn')]
                .filter(b => b.offsetWidth > 0)
                .map(b => b.getBoundingClientRect().width)"""
        )
        if len(widths) < 2:
            continue
        max_diff = max(widths) - min(widths)
        assert max_diff <= 2, f".btn-row[{i}] buttons have unequal widths: {widths}"


def test_btn_row_buttons_same_vertical_level(page):
    """All buttons in a .btn-row should sit on the same horizontal axis (±2px)."""
    if not _navigate_to_threads_detail(page):
        return

    rows = page.locator(".btn-row")
    count = rows.count()
    if count == 0:
        return

    for i in range(count):
        tops = rows.nth(i).evaluate(
            """row => [...row.querySelectorAll('button, .btn')]
                .filter(b => b.offsetWidth > 0)
                .map(b => b.getBoundingClientRect().top)"""
        )
        if len(tops) < 2:
            continue
        max_diff = max(tops) - min(tops)
        assert max_diff <= 2, f".btn-row[{i}] buttons not vertically aligned: {tops}"


def test_btn_content_vertically_centered(page):
    """Icons and text inside .btn-row buttons should be vertically centered (±3px)."""
    if not _navigate_to_threads_detail(page):
        return

    offsets = page.evaluate(
        """() => {
          const results = [];
          document.querySelectorAll('.btn-row button').forEach(btn => {
            if (btn.offsetWidth === 0) return;
            const btnRect = btn.getBoundingClientRect();
            const btnCenter = btnRect.top + btnRect.height / 2;
            const children = [...btn.children].filter(c => c.offsetWidth > 0);
            children.forEach(child => {
              const childRect = child.getBoundingClientRect();
              const childCenter = childRect.top + childRect.height / 2;
              results.push({
                tag: child.tagName,
                offset: Math.abs(btnCenter - childCenter)
              });
            });
          });
          return results;
        }"""
    )
    for item in offsets:
        assert item["offset"] <= 3, (
            f"Content {item['tag']} not centered in button: offset={item['offset']:.1f}px"
        )


def test_threads_regen_buttons_equal_width(page):
    """'Переписать' and 'История' buttons in .threads-regen-row should be equal width."""
    if not _navigate_to_threads_detail(page):
        return

    rows = page.locator(".threads-regen-row")
    count = rows.count()
    if count == 0:
        return

    for i in range(count):
        widths = rows.nth(i).evaluate(
            """row => [...row.querySelectorAll('button')]
                .filter(b => b.offsetWidth > 0)
                .map(b => b.getBoundingClientRect().width)"""
        )
        if len(widths) < 2:
            continue
        max_diff = max(widths) - min(widths)
        assert max_diff <= 2, (
            f".threads-regen-row[{i}] buttons have unequal widths: {widths}"
        )
