#!/usr/bin/env python3
"""Build icon.icns from app_icon.png.

Loads the source PNG, pads to a square (transparent), resamples at every size
macOS requires, then runs iconutil to produce icon.icns.
"""

import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'Pillow'])
    from PIL import Image, ImageOps


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


def main() -> None:
    base    = Path(__file__).parent
    src     = base / 'app_icon.png'
    iconset = base / 'icon.iconset'
    icns    = base / 'icon.icns'

    if not src.exists():
        print(f'ERROR: missing source image {src}', file=sys.stderr)
        sys.exit(1)

    iconset.mkdir(exist_ok=True)

    master = Image.open(src).convert('RGBA')
    side   = max(master.size)
    if master.size != (side, side):
        # Pad non-square source to a centered square with transparent bars.
        master = ImageOps.pad(master, (side, side), method=Image.LANCZOS,
                              color=(0, 0, 0, 0), centering=(0.5, 0.5))

    print(f'  Source: {src.name} → {side}x{side} (squared)')
    for filename, size in SIZES:
        master.resize((size, size), Image.LANCZOS).save(iconset / filename)
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
