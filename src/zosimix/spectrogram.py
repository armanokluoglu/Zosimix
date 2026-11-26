"""A spectrogram picture for the agent (DESIGN.md §5 ablation: "spectrogram-image tool on vs off", D78).

Claude can read images, so this draws what an engineer would look at: time left to right,
frequency bottom to top on a log scale (20 Hz to 20 kHz by default), loudness as brightness.
Faint horizontal lines mark 100 Hz, 1 kHz and 10 kHz. A fixed resonance shows as a bright
horizontal line that stays put while the notes move; mud as a bright band low down.

Drawn with numpy and written as PNG with the standard library (zlib), so it adds no dependency.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

WIDTH, HEIGHT = 640, 320
DB_RANGE = 80.0
GUIDES_HZ = (100.0, 1000.0, 10000.0)
# A sequential palette from near-black through blue and orange to near-white: brightness
# rises steadily, so louder always reads as brighter, in colour or in greyscale.
PALETTE = np.array([[10, 10, 20], [40, 30, 90], [120, 40, 130], [200, 70, 90], [245, 140, 50], [250, 230, 160]],
                   dtype=float)


def _colour(level: np.ndarray) -> np.ndarray:
    """level 0..1 -> RGB, interpolated along PALETTE."""
    pos = np.clip(level, 0.0, 1.0) * (len(PALETTE) - 1)
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, len(PALETTE) - 1)
    t = (pos - lo)[..., None]
    return PALETTE[lo] * (1 - t) + PALETTE[hi] * t


def image(x: np.ndarray, sr: int, lo_hz: float = 20.0, hi_hz: float = 20000.0,
          width: int = WIDTH, height: int = HEIGHT, n_fft: int = 4096) -> np.ndarray:
    """The spectrogram as an RGB array (height, width, 3), uint8."""
    mono = x.mean(axis=1) if x.ndim == 2 else x
    hop = max(1, (len(mono) - n_fft) // max(1, width - 1))
    starts = np.arange(0, max(1, len(mono) - n_fft + 1), hop)[:width]
    frames = np.stack([np.pad(mono[s:s + n_fft], (0, max(0, n_fft - len(mono[s:s + n_fft])))) for s in starts])
    power_db = 10.0 * np.log10(np.abs(np.fft.rfft(frames * np.hanning(n_fft), axis=1)) ** 2 + 1e-20)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    hi_hz = min(hi_hz, sr / 2)
    rows = np.geomspace(hi_hz, lo_hz, height)                     # top row = highest frequency
    grid = np.stack([np.interp(rows, freqs, frame) for frame in power_db], axis=1)
    top = grid.max()
    level = (grid - (top - DB_RANGE)) / DB_RANGE
    rgb = _colour(level)
    for f in GUIDES_HZ:
        if lo_hz < f < hi_hz:
            row = int(np.argmin(np.abs(rows - f)))
            rgb[row] = rgb[row] * 0.6 + 255 * 0.4                  # faint, so it doesn't hide the data
    if len(starts) < width:                                        # a very short clip: stretch to width
        idx = np.linspace(0, len(starts) - 1, width).round().astype(int)
        rgb = rgb[:, idx]
    return rgb.astype(np.uint8)


def png(rgb: np.ndarray) -> bytes:
    """Encode an RGB uint8 array as a PNG file (8-bit truecolour, no interlace)."""
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(height))     # filter byte 0 per row

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
