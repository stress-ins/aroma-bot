# Mini App Handbook UX Audit

## Main Findings

1. The reference card lacks a clear visual hierarchy.
Photo, key meaning, short description, and long-form sections compete for attention instead of leading the eye through the card.

2. The current detail view is too text-heavy.
Long paragraphs are useful as source material, but they are hard to scan on mobile without short summaries and stronger grouping.

3. The image block does not currently validate the card.
Users expect the image to confirm the raw source of the oil or practice. A generic SVG banner does not satisfy that expectation.

4. Primary and secondary sections are not separated strongly enough.
`Описание`, `НПС`, `Терапия`, `Психология`, `История`, and `Ресурс +/-` should not have equal visual weight.

5. The list and detail panels are too similar in density.
The list should stay compact and summary-driven, while the detail view should feel clearly expanded and editorial.

## Recommended Changes

1. Rebuild the top of the reference card around four layers:
- exact source photo
- title + short key line
- one compact summary block
- expandable or clearly separated detailed sections

2. Introduce compact section summaries:
- `НПС`: one-line effect first, long text second
- `Терапия`: key properties chips or summary sentence first
- `Психология`: one dominant theme first

3. Add a stronger “card passport” pattern.
For oils this should immediately answer:
- what it is
- from what raw source it is made
- what extraction is used
- what the dominant emotional/resource theme is

4. Make the list cards more informative but shorter.
Each list card should show:
- source type
- title
- one-line essence
- maybe one compact badge for `НПС` or resource theme

5. Use exact local images for oils.
The image should be a real photo of the source raw material: lavender plant, orange fruit, eucalyptus leaves, etc.

## Priority

- P1: replace generic source image with exact local photos
- P1: redesign top part of the detail card for hierarchy
- P2: add summaries/chips for faster scanability
- P2: reduce text density in the list view
