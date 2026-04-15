"""
Build a branded PowerPoint report from listings.json
Slides:
  1. Cover – date, total count
  2. Executive Summary – key stats
  3-N. One slide per suburb with ≥1 listing (table of listings)
  N+1. Methodology / footer
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pptx
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

DATA_DIR = Path("data")
LISTINGS_FILE = DATA_DIR / "listings.json"
PPTX_OUT = DATA_DIR / "Bayside_Commercial_Report.pptx"

# ── Brand ─────────────────────────────────────────────────────────────────────
NAVY  = RGBColor(0x0D, 0x21, 0x37)
GOLD  = RGBColor(0xC9, 0xA8, 0x4C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LGREY = RGBColor(0xF4, 0xF6, 0xFA)
DGREY = RGBColor(0x44, 0x44, 0x44)


def _solid_fill(shape, rgb: RGBColor):
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb


def _add_textbox(slide, left, top, width, height, text,
                 font_size=14, bold=False, color=None, align=PP_ALIGN.LEFT,
                 wrap=True, font_name="Arial"):
    txBox = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color
    return txBox


def _bg_rect(slide, left, top, width, height, color: RGBColor):
    rect = slide.shapes.add_shape(
        pptx.enum.shapes.MSO_SHAPE_TYPE.AUTO_SHAPE,  # type ignore
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    _solid_fill(rect, color)
    rect.line.fill.background()  # no border
    return rect


# ── Slide builders ─────────────────────────────────────────────────────────────

def _cover_slide(prs, total: int, new_count: int):
    slide_layout = prs.slide_layouts[6]  # blank
    slide = prs.slides.add_slide(slide_layout)

    # Full navy background
    bg = slide.shapes.add_shape(
        1, 0, 0, prs.slide_width, prs.slide_height
    )
    _solid_fill(bg, NAVY)
    bg.line.fill.background()

    # Gold accent bar
    bar = slide.shapes.add_shape(1, 0, Inches(3.6), prs.slide_width, Inches(0.08))
    _solid_fill(bar, GOLD)
    bar.line.fill.background()

    _add_textbox(slide, 0.6, 0.5, 9, 1.0,
                 "PRECISION PROPERTY", 13, True, GOLD, PP_ALIGN.LEFT)

    _add_textbox(slide, 0.6, 1.2, 9, 1.4,
                 "Bayside & Logan Corridor\nCommercial Lease Report",
                 36, True, WHITE, PP_ALIGN.LEFT, font_name="Georgia")

    _add_textbox(slide, 0.6, 3.8, 9, 0.5,
                 datetime.today().strftime("Week of %d %B %Y"),
                 14, False, GOLD, PP_ALIGN.LEFT)

    # Stats
    for i, (label, val) in enumerate([
        (f"{total}", "TOTAL LISTINGS"),
        (f"{new_count}", "NEW THIS WEEK"),
    ]):
        x = 0.6 + i * 3.2
        _add_textbox(slide, x, 4.5, 3, 0.8, val, 36, True, WHITE, PP_ALIGN.LEFT)
        _add_textbox(slide, x, 5.2, 3, 0.4, label, 11, False, GOLD, PP_ALIGN.LEFT)

    _add_textbox(slide, 0.6, 6.7, 9, 0.3,
                 "Sources: realcommercial.com.au | commercialrealestate.com.au",
                 9, False, RGBColor(0x88, 0x99, 0xAA), PP_ALIGN.LEFT)


def _summary_slide(prs, listings: list):
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Header bar
    hdr = slide.shapes.add_shape(1, 0, 0, prs.slide_width, Inches(1.1))
    _solid_fill(hdr, NAVY)
    hdr.line.fill.background()

    _add_textbox(slide, 0.4, 0.2, 9, 0.7, "Executive Summary", 24, True, WHITE)

    # Type breakdown
    type_counts = defaultdict(int)
    suburb_counts = defaultdict(int)
    for l in listings:
        type_counts[l.get("type") or "Unspecified"] += 1
        suburb_counts[l.get("suburb", "")] += 1

    top_types = sorted(type_counts.items(), key=lambda x: -x[1])[:6]
    top_suburbs = sorted(suburb_counts.items(), key=lambda x: -x[1])[:6]

    _add_textbox(slide, 0.4, 1.3, 4.5, 0.4, "By Property Type", 14, True, NAVY)
    for i, (t, c) in enumerate(top_types):
        _add_textbox(slide, 0.4, 1.8 + i * 0.42, 4.5, 0.4, f"  {t}  —  {c}", 12, False, DGREY)

    _add_textbox(slide, 5.5, 1.3, 4.5, 0.4, "Top Suburbs by Volume", 14, True, NAVY)
    for i, (s, c) in enumerate(top_suburbs):
        _add_textbox(slide, 5.5, 1.8 + i * 0.42, 4.5, 0.4, f"  {s}  —  {c} listings", 12, False, DGREY)

    # Gold footer line
    line = slide.shapes.add_shape(1, 0, Inches(7.0), prs.slide_width, Inches(0.05))
    _solid_fill(line, GOLD)
    line.line.fill.background()
    _add_textbox(slide, 0.4, 7.1, 9, 0.3,
                 "Precision Property | precisionprop.com.au | 0432 203 354",
                 9, False, RGBColor(0x88, 0x99, 0xAA))


def _suburb_slide(prs, suburb: str, rows: list):
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Header
    hdr = slide.shapes.add_shape(1, 0, 0, prs.slide_width, Inches(0.9))
    _solid_fill(hdr, NAVY)
    hdr.line.fill.background()

    _add_textbox(slide, 0.3, 0.1, 9, 0.7, suburb.upper(), 22, True, WHITE)
    _add_textbox(slide, 8.5, 0.2, 1.5, 0.5,
                 f"{len(rows)} listing{'s' if len(rows)>1 else ''}",
                 11, False, GOLD, PP_ALIGN.RIGHT)

    # Column headers
    col_labels = ["Address", "Type", "Size", "Asking Rental", "Agent", "Source"]
    col_x      = [0.2,        2.9,   4.6,   5.6,             7.1,    8.6]
    col_w      = [2.6,        1.6,   0.9,   1.4,             1.4,    1.3]

    for label, x, w in zip(col_labels, col_x, col_w):
        cell = slide.shapes.add_shape(1, Inches(x), Inches(0.95), Inches(w), Inches(0.32))
        _solid_fill(cell, GOLD)
        cell.line.fill.background()
        _add_textbox(slide, x + 0.02, 0.96, w - 0.04, 0.30, label, 8, True, NAVY)

    row_h = 0.47
    max_rows = min(len(rows), 13)

    for ri, listing in enumerate(rows[:max_rows]):
        y = 1.30 + ri * row_h
        fill_col = LGREY if ri % 2 == 0 else WHITE
        row_bg = slide.shapes.add_shape(1, 0, Inches(y), prs.slide_width, Inches(row_h - 0.03))
        _solid_fill(row_bg, fill_col)
        row_bg.line.fill.background()

        vals = [
            listing.get("address", "")[:50],
            listing.get("type", ""),
            listing.get("size", ""),
            listing.get("asking_rental", "POA"),
            listing.get("listing_agent", "")[:20],
            listing.get("source", "")[:25],
        ]

        for val, x, w in zip(vals, col_x, col_w):
            _add_textbox(slide, x + 0.02, y + 0.02, w - 0.04, row_h - 0.06,
                        str(val), 8, False, DGREY, wrap=True)

    if len(rows) > max_rows:
        _add_textbox(slide, 0.2, 1.30 + max_rows * row_h, 9, 0.3,
                     f"  + {len(rows) - max_rows} more listings — see Excel for full data",
                     9, False, DGREY)

    # Footer
    line = slide.shapes.add_shape(1, 0, Inches(7.3), prs.slide_width, Inches(0.04))
    _solid_fill(line, GOLD)
    line.line.fill.background()


# ── Main ───────────────────────────────────────────────────────────────────────

def build_pptx(listings: dict) -> Path:
    prs = Presentation()
    prs.slide_width  = Inches(10)
    prs.slide_height = Inches(7.5)

    all_rows = list(listings.values())
    from datetime import timedelta
    today_str = datetime.today().strftime("%Y-%m-%d")
    cutoff = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    new_count = sum(1 for r in all_rows if r.get("first_seen", "") >= cutoff)

    _cover_slide(prs, len(all_rows), new_count)
    _summary_slide(prs, all_rows)

    # One slide per suburb (sorted alpha)
    by_suburb = defaultdict(list)
    for r in all_rows:
        by_suburb[r.get("suburb", "Unknown")].append(r)

    for suburb in sorted(by_suburb):
        _suburb_slide(prs, suburb, by_suburb[suburb])

    prs.save(PPTX_OUT)
    print(f"PowerPoint saved → {PPTX_OUT}  ({len(all_rows)} listings, {len(by_suburb)} suburbs)")
    return PPTX_OUT


if __name__ == "__main__":
    with open(LISTINGS_FILE) as f:
        data = json.load(f)
    build_pptx(data)
