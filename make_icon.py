#!/usr/bin/env python3
"""Generate icon.icns for SaveThisVideo.

Design: dark navy rounded square, horizontal film strip spanning full width,
bold green downward arrow centered on the strip.
"""

import os
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'Pillow'])
    from PIL import Image, ImageDraw


def draw(size: int) -> Image.Image:
    s = size
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ── Background: dark navy rounded square ──────────────────────────────────
    d.rounded_rectangle(
        [0, 0, s - 1, s - 1],
        radius=int(s * 0.175),
        fill=(18, 18, 30, 255),
    )

    # ── Film strip ────────────────────────────────────────────────────────────
    sy = int(s * 0.27)          # strip top
    ey = int(s * 0.73)          # strip bottom
    sh = ey - sy                # strip total height
    ph = int(sh * 0.20)         # sprocket row height

    d.rectangle([0, sy,      s - 1, ey     ], fill=(30, 30, 50, 255))   # strip body
    d.rectangle([0, sy,      s - 1, sy + ph], fill=(10, 10, 18, 255))   # top sprocket row
    d.rectangle([0, ey - ph, s - 1, ey     ], fill=(10, 10, 18, 255))   # bottom sprocket row

    # Sprocket holes (7 per row, top and bottom)
    n      = 7
    hw     = int(ph * 0.52)
    hh     = int(ph * 0.52)
    hr     = max(1, int(hw * 0.22))
    margin = int(s * 0.06)
    gap    = (s - 2 * margin) / max(n - 1, 1)

    for i in range(n):
        cx = int(margin + i * gap)
        for cy in (sy + ph // 2, ey - ph // 2):
            d.rounded_rectangle(
                [cx - hw // 2, cy - hh // 2, cx + hw // 2, cy + hh // 2],
                radius=hr,
                fill=(210, 215, 230, 255),
            )

    # ── Down arrow (green) ────────────────────────────────────────────────────
    green = (46, 204, 113, 255)

    ct = sy + ph                    # content area top (below top sprocket row)
    cb = ey - ph                    # content area bottom
    ch = cb - ct                    # content height
    cx = s // 2

    shaft_w  = int(s * 0.115)
    head_w   = int(s * 0.30)

    shaft_top = ct + int(ch * 0.10)
    shaft_bot = ct + int(ch * 0.60)
    head_top  = shaft_bot
    head_bot  = ct + int(ch * 0.92)

    # Shaft (rectangle)
    d.rectangle(
        [cx - shaft_w // 2, shaft_top, cx + shaft_w // 2, shaft_bot],
        fill=green,
    )
    # Head (downward triangle)
    d.polygon(
        [(cx - head_w // 2, head_top),
         (cx + head_w // 2, head_top),
         (cx,               head_bot)],
        fill=green,
    )

    return img


# macOS iconset requires these exact filenames and pixel dimensions
SIZES = [
    ('icon_16x16.png',      16),
    ('icon_16x16@2x.png',   32),
    ('icon_32x32.png',      32),
    ('icon_32x32@2x.png',   64),
    ('icon_128x128.png',    128),
    ('icon_128x128@2x.png', 256),
    ('icon_256x256.png',    256),
    ('icon_256x256@2x.png', 512),
    ('icon_512x512.png',    512),
    ('icon_512x512@2x.png', 1024),
]


def main():
    base    = Path(__file__).parent
    iconset = base / 'icon.iconset'
    icns    = base / 'icon.icns'

    iconset.mkdir(exist_ok=True)

    print('  Rendering icon at all required sizes...')
    for filename, size in SIZES:
        draw(size).save(iconset / filename)
        print(f'    {size}px  →  {filename}')

    print('  Running iconutil...')
    result = subprocess.run(
        ['iconutil', '-c', 'icns', str(iconset), '-o', str(icns)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f'  ERROR: {result.stderr}', file=sys.stderr)
        sys.exit(1)

    print(f'  icon.icns  ({icns.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
