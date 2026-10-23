#!/usr/bin/env python3
"""
Renders a formerlyknownwrites quote post as a 1080x1350 PNG.

Two styles, matched to the existing posts:
  note   cream background, handwritten navy script (Caveat)
  black  near-black background, white sans (Inter)

Usage as a module:
    from render_post import render
    render("The quote text.\nSecond sentence.", "black", "bank/p0001_black_fatherhood.png")

Raises ValueError if the text will not fit cleanly, so a bad render never
ships silently.
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "fonts")

W, H = 1080, 1350
MAX_TEXT_WIDTH = 860
MAX_LINES = 9
FOOTER = "formerlyknownwrites"

STYLES = {
    "note": {
        "bg": (250, 247, 238),
        "fg": (26, 43, 95),
        "footer_fg": (70, 70, 70),
        "font": "Caveat_500Medium.ttf",
        "size": 63,
        "pitch": 69,
        "x": 116,
        "center_y": 646,
        "footer_font": "Caveat_500Medium.ttf",
        "footer_width": 319,   # measured from existing posts
        "footer_x": 113,
        "footer_ink_top": 1214,
    },
    "black": {
        "bg": (10, 10, 10),
        "fg": (240, 240, 240),
        "footer_fg": (140, 140, 140),
        "font": "Inter_400Regular.ttf",
        "size": 58,
        "pitch": 82,
        "x": 91,
        "center_y": 635,
        "footer_font": "Inter_400Regular.ttf",
        "footer_width": 344,
        "footer_x": 90,
        "footer_ink_top": 1247,
    },
}


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def _wrap(text, font, max_width):
    """Greedy word wrap. Explicit newlines in text are kept as hard breaks."""
    lines = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            continue
        cur = words[0]
        for w in words[1:]:
            trial = cur + " " + w
            if font.getlength(trial) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return _fix_orphans(lines, font, max_width)


def _fix_orphans(lines, font, max_width):
    """Avoid a lone one-word last line by pulling one word down from the line above,
    when the result still fits."""
    if len(lines) < 2:
        return lines
    last = lines[-1]
    prev_words = lines[-2].split()
    if len(last.split()) == 1 and len(prev_words) > 3:
        moved = prev_words[-1] + " " + last
        if font.getlength(moved) <= max_width:
            lines = lines[:-2] + [" ".join(prev_words[:-1]), moved]
    return lines


def _fit_footer_size(font_name, target_width):
    best = min(range(20, 70), key=lambda s: abs(_font(font_name, s).getlength(FOOTER) - target_width))
    return best


def render(text, style, out_path):
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}")
    s = STYLES[style]
    font = _font(s["font"], s["size"])
    lines = _wrap(text.strip(), font, MAX_TEXT_WIDTH)
    if not lines:
        raise ValueError("empty text")
    if len(lines) > MAX_LINES:
        raise ValueError(f"too long: {len(lines)} lines (max {MAX_LINES}): {text[:60]!r}")
    widest = max(font.getlength(l) for l in lines)
    if widest > MAX_TEXT_WIDTH + 1:
        raise ValueError(f"a single word is too wide ({widest:.0f}px): {text[:60]!r}")

    img = Image.new("RGB", (W, H), s["bg"])
    d = ImageDraw.Draw(img)

    block_h = len(lines) * s["pitch"]
    y = s["center_y"] - block_h / 2
    for line in lines:
        d.text((s["x"], y), line, font=font, fill=s["fg"])
        y += s["pitch"]

    ff_size = _fit_footer_size(s["footer_font"], s["footer_width"])
    ff = _font(s["footer_font"], ff_size)
    top_off = ff.getbbox(FOOTER)[1]
    d.text((s["footer_x"], s["footer_ink_top"] - top_off), FOOTER, font=ff, fill=s["footer_fg"])

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 4:
        print("usage: render_post.py 'text' note|black out.png")
        sys.exit(2)
    render(sys.argv[1].replace("\\n", "\n"), sys.argv[2], sys.argv[3])
    print("wrote", sys.argv[3])
