"""Draw the plugin's icon (.claude-plugin/icon.png): equaliser bars, one of them the fault (D88).

A row of blue bars shaped like a mix's spectrum, with one orange bar standing out above its
neighbours: the problem the agent finds by measuring. Same colours as the results charts.
Drawn at 4x and averaged down for smooth edges; written with the project's own PNG encoder,
so it needs no imaging library.

Usage:
    python plugin/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from zosimix.spectrogram import png

SIZE = 1024                       # the plugin directory accepts 512-2048 px squares
SCALE = 4
BACKGROUND = (18, 24, 38)         # deep navy
BLUE = (42, 120, 214)             # results chart, harness colour
ORANGE = (235, 104, 52)           # results chart, second colour
HEIGHTS = [0.34, 0.52, 0.64, 0.92, 0.58, 0.46, 0.30]     # relative bar heights; the 4th is the fault
FAULT = 3
OUT = Path(__file__).resolve().parents[1] / ".claude-plugin" / "icon.png"


def draw() -> np.ndarray:
    n = SIZE * SCALE
    img = np.empty((n, n, 3), dtype=float)
    img[:] = BACKGROUND
    yy, xx = np.mgrid[0:n, 0:n]
    margin, gap = 0.17 * n, 0.03 * n
    width = (n - 2 * margin - gap * (len(HEIGHTS) - 1)) / len(HEIGHTS)
    floor, room = 0.80 * n, 0.60 * n
    radius = width / 2
    for i, h in enumerate(HEIGHTS):
        x0 = margin + i * (width + gap)
        top = floor - h * room
        cx = x0 + radius
        # a bar with fully rounded ends: a rectangle plus a circle at each end
        body = (xx >= x0) & (xx < x0 + width) & (yy >= top + radius) & (yy <= floor - radius)
        caps = ((xx - cx) ** 2 + (yy - (top + radius)) ** 2 <= radius ** 2) | \
               ((xx - cx) ** 2 + (yy - (floor - radius)) ** 2 <= radius ** 2)
        img[body | caps] = ORANGE if i == FAULT else BLUE
    small = img.reshape(SIZE, SCALE, SIZE, SCALE, 3).mean(axis=(1, 3))     # 4x supersampling
    return np.clip(small, 0, 255).astype(np.uint8)


if __name__ == "__main__":
    OUT.write_bytes(png(draw()))
    print(f"wrote {OUT} ({SIZE}x{SIZE})")
