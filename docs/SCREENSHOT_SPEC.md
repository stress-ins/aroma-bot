# Screenshot Spec

## 13. Zone-boundary scroll captures

### Problem

The default scroll loop advances in full viewport-height increments
(0 px, 852 px, 1704 px ...). Interactive elements that cross a **forbidden
zone** — the Telegram header (y 0–55) or the iOS home indicator
(y 818–852) — may never appear in a screenshot at the exact scroll
position where they overlap.

### Solution

After the regular frame-by-frame pass, `_capture_scroll_snapshots` runs a
**zone-boundary pass**:

1. Resets scroll to 0.
2. Queries every interactive element inside the scroll container:
   `button, a[href], input, select, [role="button"], [onclick], [data-action]`.
3. For each element computes two critical scroll positions:
   - `el.absTop - ZONE_TOP_BOTTOM` — element top reaches the header bottom edge (55 px).
   - `el.absBottom - ZONE_BOTTOM_TOP` — element bottom reaches the home-indicator top edge (818 px).
4. Deduplicates positions within a **20 px tolerance**.
5. Filters out positions already captured by the frame loop (within 20 px).
6. Caps at **20 zone captures** per screen.
7. Screenshots are saved as `{sid}_zone_{N}.png` (sequential index).

### Constants

| Name | Value | Meaning |
|------|-------|---------|
| `ZONE_TOP_BOTTOM` | 55 | Bottom edge of TG header |
| `ZONE_BOTTOM_TOP` | 818 | Top edge of home indicator (852 − 34) |

### Filename pattern

```
dark_drafts-detail-carousel_zone_0.png
dark_drafts-detail-carousel_zone_1.png
```

### Gallery summary line

The run summary includes a **Zone captures** counter alongside the existing
scroll-snapshot count.
