"""Layout: touch targets, overlap, mobile safety."""
from __future__ import annotations


def test_mobile_layout_has_no_overlapping_controls(page):
    for tab_name in ["Черновики", "Планы", "Создать"]:
        {"Черновики": page.locator("#btnTabDrafts"), "Планы": page.locator("#btnTabPlans"), "Создать": page.locator("#btnTabCreate")}[tab_name].click()
        page.wait_for_timeout(100)

        overlaps = page.evaluate(
            """
            () => {
              const controls = [...document.querySelectorAll('button, select, input, textarea')]
                .filter((node) => {
                  const style = getComputedStyle(node);
                  const rect = node.getBoundingClientRect();
                  return !node.hidden && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                })
                .map((node) => ({
                  text: (node.innerText || node.value || node.textContent || '').trim().slice(0, 40),
                  x: node.getBoundingClientRect().x,
                  y: node.getBoundingClientRect().y,
                  w: node.getBoundingClientRect().width,
                  h: node.getBoundingClientRect().height,
                }));
              const bad = [];
              for (let i = 0; i < controls.length; i++) {
                for (let j = i + 1; j < controls.length; j++) {
                  const a = controls[i];
                  const b = controls[j];
                  const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
                  const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
                  const area = ix * iy;
                  if (area > 150) {
                    bad.push({ a: a.text, b: b.text, area });
                  }
                }
              }
              return bad;
            }
            """
        )
        assert overlaps == []


def test_mobile_primary_controls_have_comfortable_hit_targets(page):
    metrics = page.evaluate(
        """
        () => {
          const selectors = ['.mode-button', '.tab-button', '.icon-corner-button', '.secondary-button', '.primary-button', '.back-button.visible', '.bottom-tab-btn'];
          return selectors.flatMap((selector) =>
            [...document.querySelectorAll(selector)]
              .filter((node) => {
                const style = getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
              })
              .map((node) => ({
                selector,
                text: (node.textContent || '').trim().slice(0, 40),
                width: Math.round(node.getBoundingClientRect().width),
                height: Math.round(node.getBoundingClientRect().height),
              }))
          );
        }
        """
    )
    bad = [item for item in metrics if item["height"] < 44]
    assert bad == []


def test_mobile_detail_actions_do_not_overlap(page):
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(100)
    page.evaluate("window.goBackToList()")
    page.locator(".draft-card").first.wait_for(state="visible")
    page.locator(".draft-card").first.click()
    page.wait_for_timeout(100)

    overlaps = page.evaluate(
        """
        () => {
          const root = document.querySelector('#draftDetail');
          const controls = [...root.querySelectorAll('button, select, input, textarea')]
            .filter((node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return !node.hidden && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            })
            .map((node) => ({
              text: (node.innerText || node.value || node.textContent || '').trim().slice(0, 50),
              x: node.getBoundingClientRect().x,
              y: node.getBoundingClientRect().y,
              w: node.getBoundingClientRect().width,
              h: node.getBoundingClientRect().height,
            }));
          const bad = [];
          for (let i = 0; i < controls.length; i++) {
            for (let j = i + 1; j < controls.length; j++) {
              const a = controls[i];
              const b = controls[j];
              const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
              const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
              if ((ix * iy) > 100) bad.push({ a: a.text, b: b.text, area: ix * iy });
            }
          }
          return bad;
        }
        """
    )
    assert overlaps == []


def test_no_horizontal_overflow_on_mobile(page):
    """No panel or action row should overflow the viewport width on mobile."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.reload()
    page.wait_for_timeout(100)

    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(100)
    page.evaluate("window.goBackToList()")
    first_card = page.locator(".draft-card").first
    if first_card.count():
        first_card.click()
        page.wait_for_timeout(100)

    overflows = page.evaluate(
        """
        () => {
            const results = [];
            document.querySelectorAll('.panel, .section, .actions-row, .detail-actions, .detail-icon-actions, .actions-row-pair').forEach(el => {
                if (el.scrollWidth > el.clientWidth + 2) {
                    results.push({
                        cls: el.className.slice(0, 60),
                        scrollWidth: el.scrollWidth,
                        clientWidth: el.clientWidth,
                    });
                }
            });
            return results;
        }
        """
    )
    assert overflows == [], f"Elements overflow viewport: {overflows}"


def test_detail_card_title_not_clipped_on_mobile(page):
    """Every detail card type: title must be fully visible, not clipped at top."""
    page.locator("#btnTabDrafts").click()
    page.wait_for_timeout(100)
    page.evaluate("window.goBackToList()")

    cards = page.locator(".draft-card")
    cards.first.wait_for(state="visible")
    count = cards.count()

    for i in range(count):
        page.evaluate("window.goBackToList()")
        page.wait_for_timeout(100)
        cards.nth(i).click()
        page.wait_for_timeout(200)

        title = page.locator(".detail-title").first
        if not title.count():
            continue

        box = title.bounding_box()
        assert box is not None, f"Card {i}: title has no bounding box"
        assert box["y"] >= 0, f"Card {i}: title clipped at top (y={box['y']})"
        assert box["y"] + box["height"] <= 932, f"Card {i}: title below viewport"
        assert title.inner_text().strip(), f"Card {i}: title is empty"


def test_handbook_detail_title_not_clipped(page):
    """Handbook card detail: title must be visible."""
    page.locator("#btnTabHandbook").click()
    page.wait_for_timeout(100)

    card = page.locator(".reference-card").first
    if card.count():
        card.click()
        page.wait_for_timeout(200)

        title = page.locator(".detail-title").first
        if title.count():
            box = title.bounding_box()
            assert box is not None
            assert box["y"] >= 0


def test_themed_controls_have_no_overlaps(themed_page):
    """No controls overlap in either theme."""
    for tab_id in ["#btnTabDrafts", "#btnTabPlans", "#btnTabCreate"]:
        themed_page.locator(tab_id).click()
        themed_page.wait_for_timeout(100)

        overlaps = themed_page.evaluate(
            """
            () => {
              const controls = [...document.querySelectorAll('button, select, input, textarea')]
                .filter(n => {
                  const s = getComputedStyle(n), r = n.getBoundingClientRect();
                  return !n.hidden && s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0;
                })
                .map(n => {
                  const r = n.getBoundingClientRect();
                  return { text: (n.innerText||'').trim().slice(0,40), x: r.x, y: r.y, w: r.width, h: r.height };
                });
              const bad = [];
              for (let i = 0; i < controls.length; i++)
                for (let j = i+1; j < controls.length; j++) {
                  const a = controls[i], b = controls[j];
                  const ix = Math.max(0, Math.min(a.x+a.w, b.x+b.w) - Math.max(a.x, b.x));
                  const iy = Math.max(0, Math.min(a.y+a.h, b.y+b.h) - Math.max(a.y, b.y));
                  if (ix*iy > 150) bad.push({a: a.text, b: b.text, area: ix*iy});
                }
              return bad;
            }
            """
        )
        assert overlaps == [], f"Overlapping controls on {tab_id}: {overlaps}"
