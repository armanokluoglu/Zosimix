"""The EQ filters shared by the faults and the offline engine, built to behave like FL's
Parametric EQ 2 (D60, D61).

PEQ2 keeps the shape of the ideal analog filter all the way up the spectrum. The usual
digital recipe (the bilinear transform, which pedalboard uses) squeezes a filter as it
nears 22 kHz: the same peak measured up to 1.7 dB different from FL's at 8 kHz. So each
band here is a "magnitude-matched" biquad (M. Vicanek, "Matched Second Order Digital
Filters", 2016):

  - poles: the analog filter's poles, mapped exactly with z = exp(s / sample_rate)
  - zeros: chosen so the digital magnitude equals the analog magnitude at three
    frequencies: 0 Hz, the Nyquist frequency, and the band's own frequency.

The analog filters, and so the meaning of gain and Q, are the "Audio EQ Cookbook" (RBJ)
ones that pedalboard also uses. A band means the same as before; only the top of the
spectrum changes. High-pass and low-pass are second order (12 dB/octave), like PEQ2's
default slope. For them Q sets the bump at the cutoff: 0.707 gives no bump.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt

BUTTERWORTH_Q = 1 / np.sqrt(2)     # high-/low-pass with no bump at the cutoff


def analog(type_: str, gain_db: float, q: float) -> tuple[np.ndarray, np.ndarray]:
    """(numerator, denominator) of the analog filter in s = j*f/freq, highest power first."""
    a = 10 ** (gain_db / 40)                       # the cookbook's "A"
    if type_ == "peaking":
        return np.array([1, a / q, 1]), np.array([1, 1 / (a * q), 1])
    if type_ == "low_shelf":
        k = np.sqrt(a) / q
        return a * np.array([1, k, a]), np.array([a, k, 1])
    if type_ == "high_shelf":
        k = np.sqrt(a) / q
        return a * np.array([a, k, 1]), np.array([1, k, a])
    if type_ == "lowpass":
        return np.array([0, 0, 1]), np.array([1, 1 / q, 1])
    if type_ == "highpass":
        return np.array([1, 0, 0]), np.array([1, 1 / q, 1])
    raise ValueError(f"unknown EQ type {type_!r}")


def _analog_power(num: np.ndarray, den: np.ndarray, f_rel: float) -> float:
    """|H(j*f_rel)|^2 of the analog filter, with frequency relative to the band's own."""
    s = 1j * f_rel
    return float(abs(np.polyval(num, s) / np.polyval(den, s)) ** 2)


def biquad(type_: str, freq_hz: float, gain_db: float, q: float, sr: int) -> np.ndarray:
    """One band as a second-order section [b0, b1, b2, 1, a1, a2] for scipy's sosfilt."""
    num, den = analog(type_, gain_db, q)

    # Poles: map the analog poles (in rad/s) exactly onto the z-plane.
    poles = np.exp(np.roots(den) * 2 * np.pi * freq_hz / sr)
    a1, a2 = float(-(poles[0] + poles[1]).real), float((poles[0] * poles[1]).real)

    # Zeros: Vicanek's trick. Writing phi1 = sin^2(w/2), phi0 = 1 - phi1, phi2 = 4*phi0*phi1,
    # the squared magnitude of any biquad polynomial c(z) is C0*phi0 + C1*phi1 + C2*phi2,
    # with C0 = (c0+c1+c2)^2, C1 = (c0-c1+c2)^2, C2 = -4*c0*c2. Matching the analog power
    # at 0 Hz, Nyquist and the band frequency gives three linear equations for B0, B1, B2.
    def phis(w: float) -> tuple[float, float, float]:
        p1 = np.sin(w / 2) ** 2
        return 1 - p1, p1, 4 * (1 - p1) * p1

    def den_power(w: float) -> float:
        p0, p1, p2 = phis(w)
        return (1 + a1 + a2) ** 2 * p0 + (1 - a1 + a2) ** 2 * p1 - 4 * a2 * p2

    nyquist_rel = sr / 2 / freq_hz
    w_band = 2 * np.pi * freq_hz / sr
    b0_sq = _analog_power(num, den, 0.0) * den_power(0.0)
    b1_sq = _analog_power(num, den, nyquist_rel) * den_power(np.pi)
    p0, p1, p2 = phis(w_band)
    b2_term = (_analog_power(num, den, 1.0) * den_power(w_band) - b0_sq * p0 - b1_sq * p1) / p2

    # Back from (B0, B1, B2) to the numerator coefficients (the minimum-phase solution).
    r0, r1 = np.sqrt(b0_sq), np.sqrt(b1_sq)
    w_mid = (r0 + r1) / 2
    b0 = (w_mid + np.sqrt(max(w_mid ** 2 + b2_term, 0.0))) / 2
    b1 = (r0 - r1) / 2
    b2 = -b2_term / (4 * b0)
    return np.array([b0, b1, b2, 1.0, a1, a2])


def apply(x: np.ndarray, bands: list[tuple[str, float, float, float]], sr: int) -> np.ndarray:
    """Filter audio x, shape (frames, channels), through bands [(type, freq_hz, gain_db, q), ...]."""
    if not bands:
        return x.copy()
    sos = np.array([biquad(t, f, g, q, sr) for t, f, g, q in bands])
    return sosfilt(sos, np.asarray(x, dtype=np.float64), axis=0)


def response_db(bands: list[tuple[str, float, float, float]], freqs: np.ndarray, sr: int) -> np.ndarray:
    """The digital magnitude response in dB at `freqs`, for tests and calibration."""
    z = np.exp(-1j * 2 * np.pi * np.asarray(freqs) / sr)
    h = np.ones_like(z)
    for t, f, g, q in bands:
        b0, b1, b2, _, a1, a2 = biquad(t, f, g, q, sr)
        h = h * (b0 + b1 * z + b2 * z ** 2) / (1 + a1 * z + a2 * z ** 2)
    return 20 * np.log10(np.abs(h) + 1e-300)
