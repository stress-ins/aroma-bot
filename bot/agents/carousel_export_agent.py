"""Carousel Export Agent — Enhanced PPTX export with placement data + Canva correction learning."""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path

from bot.services.drafts_store import get_draft, update_draft

logger = logging.getLogger(__name__)

_CORRECTIONS_LOG = Path(__file__).parent.parent.parent / "data" / "placement_corrections_log.jsonl"


# ── 1. Build PPTX from placement data ─────────────────────────────────────────

def build_pptx_from_placement(
    slides: list[str],
    images: list[bytes | None],
    placement_data: dict[str, dict] | None = None,
) -> bytes:
    """Build PPTX using Vision-based placement_data instead of heuristic.

    Falls back to _find_text_zone() for slides without placement data.
    """
    from pptx import Presentation
    from pptx.util import Emu, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.oxml.ns import qn as _qn
    from lxml import etree as _etree

    from bot.handlers.carousel import (
        _find_text_zone,
        _embed_font_in_pptx,
        _SLIDE_EMU,
        _FONT_NAME,
    )

    BEIGE = RGBColor(0xF2, 0xE8, 0xD9)
    DARK = RGBColor(0x3D, 0x2B, 0x1F)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)

    prs = Presentation()
    prs.slide_width = Emu(_SLIDE_EMU)
    prs.slide_height = Emu(_SLIDE_EMU)
    blank = prs.slide_layouts[6]

    for i, text in enumerate(slides):
        slide = prs.slides.add_slide(blank)
        img_bytes = images[i] if i < len(images) else None

        # Determine placement
        pd = placement_data.get(str(i)) if placement_data else None

        if img_bytes:
            slide.shapes.add_picture(
                io.BytesIO(img_bytes), Emu(0), Emu(0), Emu(_SLIDE_EMU), Emu(_SLIDE_EMU),
            )

            if pd:
                top_frac = pd.get("top", 0.63)
                h_frac = pd.get("height", 0.32)
                left_frac = pd.get("left", 0.08)
                w_frac = pd.get("width", 0.84)
                text_color = WHITE if pd.get("text_color", "light") == "light" else DARK
            else:
                top_frac, h_frac = _find_text_zone(img_bytes)
                left_frac, w_frac = 0.0, 1.0  # full width (matches original _build_pptx)
                text_color = WHITE
        else:
            bg = slide.shapes.add_shape(1, Emu(0), Emu(0), Emu(_SLIDE_EMU), Emu(_SLIDE_EMU))
            bg.fill.solid()
            bg.fill.fore_color.rgb = BEIGE
            bg.line.color.rgb = BEIGE
            text_color = DARK
            top_frac, h_frac = 0.32, 0.36
            left_frac, w_frac = 0.0, 1.0
            pd = None

        # Calculate positions — use placement_data left/width if available
        if pd and img_bytes:
            margin_left = Emu(int(_SLIDE_EMU * left_frac))
            box_w = Emu(int(_SLIDE_EMU * w_frac))
        else:
            margin_left = Emu(80000)
            box_w = Emu(_SLIDE_EMU) - margin_left * 2

        pad = Emu(55000)
        box_top = Emu(int(_SLIDE_EMU * top_frac))
        box_h = Emu(int(_SLIDE_EMU * h_frac))

        # Semi-transparent overlay behind text
        if img_bytes:
            overlay = slide.shapes.add_shape(
                1,
                margin_left - pad, box_top - pad,
                box_w + pad * 2, box_h + pad * 2,
            )
            overlay.fill.solid()
            overlay.fill.fore_color.rgb = RGBColor(0x18, 0x0E, 0x08)
            overlay.line.fill.background()
            sp_pr = overlay._element.spPr
            solid = sp_pr.find(".//" + _qn("a:solidFill"))
            if solid is not None:
                clr = solid.find(_qn("a:srgbClr"))
                if clr is not None:
                    alpha_el = _etree.SubElement(clr, _qn("a:alpha"))
                    alpha_el.set("val", "58000")

        txBox = slide.shapes.add_textbox(margin_left, box_top, box_w, box_h)
        txBox.fill.background()
        tf = txBox.text_frame
        tf.word_wrap = True

        p_txt = tf.paragraphs[0]
        align_val = pd.get("text_align", "left") if pd else "left"
        p_txt.alignment = PP_ALIGN.CENTER if align_val == "center" else PP_ALIGN.LEFT
        r_txt = p_txt.add_run()
        r_txt.text = text
        r_txt.font.name = _FONT_NAME
        r_txt.font.size = Pt(24)
        r_txt.font.bold = True
        r_txt.font.color.rgb = text_color

    out = io.BytesIO()
    prs.save(out)
    return _embed_font_in_pptx(out.getvalue())


# ── 2. Extract text positions from PPTX ───────────────────────────────────────

def extract_text_positions(pptx_bytes: bytes) -> list[dict | None]:
    """Extract text box positions from each slide as fractions of slide size.

    Returns list of dicts with top/left/width/height as fractions, or None.
    """
    from pptx import Presentation
    from pptx.util import Emu

    prs = Presentation(io.BytesIO(pptx_bytes))
    slide_w = prs.slide_width or Emu(1080 * 9525)
    slide_h = prs.slide_height or Emu(1080 * 9525)

    results: list[dict | None] = []
    for slide in prs.slides:
        text_shapes = [s for s in slide.shapes if s.has_text_frame and s.text.strip()]
        if not text_shapes:
            results.append(None)
            continue
        # Pick the shape with the most text
        shape = max(text_shapes, key=lambda s: len(s.text))
        results.append({
            "top": shape.top / slide_h,
            "left": shape.left / slide_w,
            "width": shape.width / slide_w,
            "height": shape.height / slide_h,
        })
    return results


# ── 3. Compute corrections ────────────────────────────────────────────────────

def compute_corrections(
    proposed: list[dict | None],
    actual: list[dict | None],
) -> list[dict]:
    """Compute deltas between proposed and actual placement for each slide."""
    from bot.agents.carousel_preview_agent import SLIDE_ROLES

    corrections: list[dict] = []
    for i in range(min(len(proposed), len(actual))):
        p = proposed[i]
        a = actual[i]
        if p is None or a is None:
            continue
        delta = {}
        for key in ("top", "left", "width", "height"):
            if key in p and key in a:
                delta[key] = round(a[key] - p[key], 4)
        role = SLIDE_ROLES[i] if i < len(SLIDE_ROLES) else "unknown"
        corrections.append({"slide_index": i, "role": role, "delta": delta})
    return corrections


# ── 4. Save corrections ──────────────────────────────────────────────────────

async def save_corrections(draft_id: str, corrections: list[dict]) -> None:
    """Save placement corrections to draft payload and JSONL log."""
    # Append to JSONL file
    _CORRECTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_CORRECTIONS_LOG, "a") as f:
        for c in corrections:
            entry = {"draft_id": draft_id, **c}
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Save to draft payload
    draft = await get_draft(draft_id)
    if not draft:
        return
    payload = dict(draft.payload)
    existing = payload.get("placement_corrections", [])
    existing.extend(corrections)
    payload["placement_corrections"] = existing
    await update_draft(draft_id, payload=payload)


# ── 5. Get aggregate bias ────────────────────────────────────────────────────

def get_aggregate_bias(role: str) -> dict:
    """Read JSONL corrections, filter by role, return mean delta.

    Returns empty dict if fewer than 5 records for this role.
    """
    if not _CORRECTIONS_LOG.exists():
        return {}

    deltas: list[dict] = []
    try:
        with open(_CORRECTIONS_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("role") == role and "delta" in entry:
                    deltas.append(entry["delta"])
    except Exception:
        return {}

    if len(deltas) < 5:
        return {}

    # Compute mean delta
    keys = ("top", "left", "width", "height")
    result: dict[str, float] = {}
    for key in keys:
        values = [d[key] for d in deltas if key in d]
        if values:
            result[key] = round(sum(values) / len(values), 4)
    return result
