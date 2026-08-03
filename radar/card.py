"""Generate the daily social image — a 1080x1080 square for Instagram/Facebook/LinkedIn.

Deliberately plain: one big number, one label, one hook, one takeaway. Posts that
try to show five things get scrolled past. The colour of the stat is driven by
its sign, so the chart reads correctly before a word is processed.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 1080
MARGIN = 84

INK = (18, 22, 32)
INK_SOFT = (104, 114, 134)
PAPER = (250, 250, 249)
ACCENT = (17, 94, 89)
UP = (4, 120, 87)
DOWN = (190, 40, 46)
RULE = (222, 224, 228)

FONT_DIRS = [Path("C:/Windows/Fonts")]
FONT_CANDIDATES = {
    "bold": ["segoeuib.ttf", "seguibl.ttf", "arialbd.ttf", "calibrib.ttf"],
    "semi": ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"],
    "regular": ["segoeui.ttf", "arial.ttf", "calibri.ttf"],
}


def _font(kind: str, size: int):
    for name in FONT_CANDIDATES[kind]:
        for d in FONT_DIRS:
            p = d / name
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except Exception:
                    continue
    return ImageFont.load_default(size)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _stat_colour(stat: str):
    s = (stat or "").strip()
    if s.startswith("-") or s.startswith("−") or "▼" in s:
        return DOWN
    if s.startswith("+") or "▲" in s:
        return UP
    return ACCENT


def make_card(analysis: dict, day: str, out_path: Path,
              brand: str = "60 SECOND FINANCE") -> Path:
    sp = analysis.get("social_post", {}) or {}
    stat = str(sp.get("card_stat", "") or "").strip()
    label = str(sp.get("card_label", "") or "").strip()
    hook = str(sp.get("hook", "") or "").strip()
    takeaway = str(sp.get("takeaway", "") or "").strip()

    img = Image.new("RGB", (SIZE, SIZE), PAPER)
    d = ImageDraw.Draw(img)
    inner = SIZE - 2 * MARGIN

    # Header: brand + date
    f_brand = _font("bold", 30)
    d.text((MARGIN, MARGIN - 20), brand, font=f_brand, fill=ACCENT)
    f_date = _font("regular", 27)
    dtxt = day
    d.text((SIZE - MARGIN - d.textlength(dtxt, font=f_date), MARGIN - 17),
           dtxt, font=f_date, fill=INK_SOFT)
    d.line([(MARGIN, MARGIN + 32), (SIZE - MARGIN, MARGIN + 32)], fill=RULE, width=2)

    y = MARGIN + 96

    # The number — shrink to fit rather than overflow
    if stat:
        size = 210
        f_stat = _font("bold", size)
        while d.textlength(stat, font=f_stat) > inner and size > 70:
            size -= 8
            f_stat = _font("bold", size)
        d.text((MARGIN, y), stat, font=f_stat, fill=_stat_colour(stat))
        y += int(size * 1.22)          # clear the font's descender

    if label:
        f_label = _font("semi", 40)
        for line in _wrap(d, label.upper(), f_label, inner)[:2]:
            d.text((MARGIN, y), line, font=f_label, fill=INK_SOFT)
            y += 52
        y += 40

    # The takeaway is anchored to the bottom, so measure it first and give the
    # hook whatever vertical space is left. Shrinking the hook is better than
    # dropping either block: both carry meaning.
    take_lines, f_take, rule_y = [], _font("regular", 38), None
    if takeaway:
        take_lines = _wrap(d, takeaway, f_take, inner)[:4]
        block_h = len(take_lines) * int(f_take.size * 1.35)
        take_top = SIZE - MARGIN - 92 - block_h
        rule_y = take_top - 46

    if hook:
        ceiling = (rule_y - 34) if rule_y else (SIZE - MARGIN - 70)
        f_hook = _font("bold", 62)
        lines = _wrap(d, hook, f_hook, inner)
        while (f_hook.size > 34 and
               y + len(lines) * int(f_hook.size * 1.2) > ceiling):
            f_hook = _font("bold", f_hook.size - 3)
            lines = _wrap(d, hook, f_hook, inner)
        for line in lines:
            d.text((MARGIN, y), line, font=f_hook, fill=INK)
            y += int(f_hook.size * 1.2)

    if take_lines:
        d.line([(MARGIN, rule_y), (MARGIN + 96, rule_y)], fill=ACCENT, width=5)
        ty = rule_y + 46
        for line in take_lines:
            d.text((MARGIN, ty), line, font=f_take, fill=INK_SOFT)
            ty += int(f_take.size * 1.35)

    # Footer
    f_foot = _font("regular", 25)
    d.line([(MARGIN, SIZE - MARGIN - 46), (SIZE - MARGIN, SIZE - MARGIN - 46)],
           fill=RULE, width=2)
    d.text((MARGIN, SIZE - MARGIN - 30),
           "Not investment advice · Sources in daily brief",
           font=f_foot, fill=INK_SOFT)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path
