# Button Layout Rules

## When to use which class

| Class | Use case | Layout |
|-------|----------|--------|
| `.btn-row` | Row of 2+ buttons that must be equal width | `flex` + `flex: 1` on children |
| `.btn-row--icons` | Icon-only buttons (square, equal size) | `flex: 1` + `aspect-ratio: 1` |
| `.actions-row` | General action row (single button, mixed content) | `flex` without forced equal width |
| `.detail-icon-actions` | Fixed 44×44 icon buttons with grid on mobile | `grid` layout |
| `.threads-regen-row` | "Переписать"/"История" pair (also uses `.btn-row`) | `flex` + `flex: 1` |

## DO / DON'T

**DO:**
- Add `.btn-row` when you need 2+ buttons of equal width in a row
- Combine `.btn-row` with existing classes (e.g. `.threads-regen-row.btn-row`)
- Use `gap` on the row, not margins on individual buttons
- Call `lucide.createIcons()` after dynamic DOM renders with icons

**DON'T:**
- Don't set explicit `width` on buttons inside `.btn-row` — `flex: 1` handles it
- Don't replace `.detail-icon-actions` with `.btn-row--icons` — they serve different purposes
- Don't use `.btn-row` for single-button rows — use `.actions-row` instead
- Don't nest `.btn-row` inside another `.btn-row`

## How to add a new screen to tests

1. Open `tests/ui/test_button_layout.py`
2. Add navigation to the new screen (tab click + optional card click)
3. Use `.btn-row` selector to find button rows
4. Assert equal widths (±2px) and vertical alignment (±2px)

## How to verify locally

```bash
# Run only button layout tests
.venv/bin/python -m pytest tests/ui/test_button_layout.py -v

# Run all UI tests
.venv/bin/python -m pytest tests/ui/ -q

# Take a screenshot for visual verification
# (use Playwright codegen or add page.screenshot() in a test)
```

## Checklist when a test fails

1. **Unequal widths:** Check that the parent has `.btn-row` class and buttons don't have explicit `width` or `max-width`
2. **Vertical misalignment:** Check for different `padding`, `font-size`, or `line-height` on buttons
3. **Content not centered:** Ensure `align-items: center` and `justify-content: center` are not overridden
4. **Regen row issue:** Verify `.threads-regen-row` still has both `.btn-row` class and `> button { flex: 1 }`
