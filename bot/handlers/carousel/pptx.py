"""PPTX generation for carousel slides."""
from __future__ import annotations

import io
import logging
import zipfile

from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

from bot.handlers.carousel.generation import (
    _FONT_PATH,
    _FONT_NAME,
    _SLIDE_EMU,
    _find_text_zone,
)

logger = logging.getLogger(__name__)

_FONT_REL_ID = "rIdDeldedaRegular"


def _embed_font_in_pptx(pptx_bytes: bytes) -> bytes:
    """Embed DeldedaOpen.ttf into the PPTX ZIP so the font travels with the file."""
    if not _FONT_PATH.exists():
        logger.warning("Font file not found: %s -- skipping font embedding", _FONT_PATH)
        return pptx_bytes

    font_data = _FONT_PATH.read_bytes()
    inp = io.BytesIO(pptx_bytes)
    out = io.BytesIO()

    font_rel_entry = (
        f'<Relationship Id="{_FONT_REL_ID}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/font" '
        f'Target="fonts/font1.ttf"/>'
    ).encode()

    font_xml_entry = (
        f'<p:embeddedFontLst>'
        f'<p:embeddedFont>'
        f'<p:font typeface="{_FONT_NAME}" charset="0" pitchFamily="32"/>'
        f'<p:regular r:id="{_FONT_REL_ID}"/>'
        f'</p:embeddedFont>'
        f'</p:embeddedFontLst>'
    ).encode()

    content_type_entry = (
        b'<Override PartName="/ppt/fonts/font1.ttf" '
        b'ContentType="application/x-fontdata"/>'
    )

    with zipfile.ZipFile(inp, "r") as zin, \
         zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:

        for item in zin.infolist():
            data = zin.read(item.filename)

            if item.filename == "ppt/_rels/presentation.xml.rels":
                data = data.replace(b"</Relationships>", font_rel_entry + b"</Relationships>")

            elif item.filename == "ppt/presentation.xml":
                data = data.replace(b"</p:presentation>", font_xml_entry + b"</p:presentation>")

            elif item.filename == "[Content_Types].xml":
                data = data.replace(b"</Types>", content_type_entry + b"</Types>")

            zout.writestr(item, data)

        # Add the font binary
        zout.writestr("ppt/fonts/font1.ttf", font_data)

    return out.getvalue()


def _build_pptx(slides: list[str], images: list[bytes | None] | None = None) -> bytes:
    BEIGE = RGBColor(0xF2, 0xE8, 0xD9)
    DARK  = RGBColor(0x3D, 0x2B, 0x1F)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)

    prs = Presentation()
    prs.slide_width  = Emu(_SLIDE_EMU)
    prs.slide_height = Emu(_SLIDE_EMU)
    blank = prs.slide_layouts[6]

    for i, text in enumerate(slides):
        slide = prs.slides.add_slide(blank)
        img_bytes = (images[i] if images and i < len(images) else None)

        if img_bytes:
            slide.shapes.add_picture(
                io.BytesIO(img_bytes), Emu(0), Emu(0), Emu(_SLIDE_EMU), Emu(_SLIDE_EMU)
            )
            text_color = WHITE
            top_frac, h_frac = _find_text_zone(img_bytes)
        else:
            bg = slide.shapes.add_shape(1, Emu(0), Emu(0), Emu(_SLIDE_EMU), Emu(_SLIDE_EMU))
            bg.fill.solid()
            bg.fill.fore_color.rgb = BEIGE
            bg.line.color.rgb = BEIGE
            text_color = DARK
            top_frac, h_frac = 0.32, 0.36   # centre for plain background

        pad     = Emu(55000)
        margin  = Emu(80000)
        box_top = Emu(int(_SLIDE_EMU * top_frac))
        box_h   = Emu(int(_SLIDE_EMU * h_frac))

        # Semi-transparent dark overlay behind text (only when image is present)
        if img_bytes:
            from pptx.oxml.ns import qn as _qn
            from lxml import etree as _etree
            overlay = slide.shapes.add_shape(
                1,
                margin - pad, box_top - pad,
                Emu(_SLIDE_EMU) - margin * 2 + pad * 2, box_h + pad * 2,
            )
            overlay.fill.solid()
            overlay.fill.fore_color.rgb = RGBColor(0x18, 0x0E, 0x08)
            overlay.line.fill.background()
            # Set 58% opacity via OOXML (val=58000 means 58% opaque)
            sp_pr = overlay._element.spPr
            solid = sp_pr.find(".//" + _qn("a:solidFill"))
            if solid is not None:
                clr = solid.find(_qn("a:srgbClr"))
                if clr is not None:
                    alpha_el = _etree.SubElement(clr, _qn("a:alpha"))
                    alpha_el.set("val", "58000")

        txBox = slide.shapes.add_textbox(
            margin, box_top, Emu(_SLIDE_EMU) - margin * 2, box_h
        )
        txBox.fill.background()
        tf = txBox.text_frame
        tf.word_wrap = True

        # Only the slide text -- no labels
        p_txt = tf.paragraphs[0]
        p_txt.alignment = PP_ALIGN.LEFT
        r_txt = p_txt.add_run()
        r_txt.text = text
        r_txt.font.name = _FONT_NAME
        r_txt.font.size = Pt(24)
        r_txt.font.bold = True
        r_txt.font.color.rgb = text_color

    out = io.BytesIO()
    prs.save(out)
    return _embed_font_in_pptx(out.getvalue())
