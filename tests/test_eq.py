"""The shared EQ filters (D61): analog-matched, so they behave like FL's Parametric EQ 2."""

import json
from pathlib import Path

import numpy as np
import pytest

from zosimix import eq

SR = 44100
CALIBRATION = Path(__file__).resolve().parents[1] / "fl_bridge" / "calibration" / "audio-eq.json"


def analog_db(type_, freq, gain, q, freqs):
    num, den = eq.analog(type_, gain, q)
    s = 1j * np.asarray(freqs) / freq
    return 20 * np.log10(np.abs(np.polyval(num, s) / np.polyval(den, s)) + 1e-300)


@pytest.mark.parametrize("type_", ["peaking", "low_shelf", "high_shelf"])
def test_zero_gain_band_is_transparent(type_):
    x = np.random.default_rng(0).standard_normal((4096, 2))
    assert np.allclose(eq.apply(x, [(type_, 1000, 0.0, 2.0)], SR), x, atol=1e-9)


@pytest.mark.parametrize(("type_", "freq", "gain", "q", "tol_db"), [
    ("peaking", 8000, 12, 8, 0.1), ("peaking", 100, -9, 1, 0.1), ("low_shelf", 200, 6, 0.7, 0.1),
    ("high_shelf", 6000, -6, 0.7, 0.1), ("highpass", 80, 0, eq.BUTTERWORTH_Q, 0.1),
    # A two-pole digital low-pass can't follow the ideal roll-off right up to Nyquist: it
    # drifts 0.1 dB by 10 kHz and 0.9 dB by 17 kHz, where it is 20 dB down. FL's does too (D61).
    ("lowpass", 5000, 0, 2, 1.0),
])
def test_follows_the_analog_shape_up_to_the_top(type_, freq, gain, q, tol_db):
    """The point of the matched design: no squeeze near Nyquist (bilinear filters drift here)."""
    freqs = np.geomspace(20, 20000, 500)
    digital, ideal = eq.response_db([(type_, freq, gain, q)], freqs, SR), analog_db(type_, freq, gain, q, freqs)
    passband = ideal > -20                             # deep stopbands don't matter
    assert np.abs(digital - ideal)[passband].max() < tol_db


def test_butterworth_highpass_is_3db_down_at_cutoff_and_12db_per_octave():
    at_50, at_100, at_cutoff = eq.response_db([("highpass", 400, 0, eq.BUTTERWORTH_Q)], [50, 100, 400], SR)
    assert at_cutoff == pytest.approx(-3.01, abs=0.05)
    assert at_100 - at_50 == pytest.approx(12, abs=0.3)    # one octave, well below the cutoff


@pytest.mark.parametrize(("freq", "gain", "q"), [(300, 12, 8), (8000, 12, 8), (250, 9, 1)])
def test_a_cut_undoes_a_boost(freq, gain, q):
    """Resonance and mud faults are peaks; the same band with the opposite gain must undo them."""
    x = np.random.default_rng(1).standard_normal((SR * 2, 2))
    y = eq.apply(eq.apply(x, [("peaking", freq, gain, q)], SR), [("peaking", freq, -gain, q)], SR)
    assert 10 * np.log10(((y - x) ** 2).sum() / (x ** 2).sum()) < -40


def test_apply_and_response_agree():
    band = [("peaking", 1500, 6, 2), ("highpass", 60, 0, 0.9)]
    impulse = np.zeros((1 << 15, 1))
    impulse[0] = 1
    h = np.fft.rfft(eq.apply(impulse, band, SR)[:, 0])
    freqs = np.fft.rfftfreq(1 << 15, 1 / SR)
    pick = (freqs > 30) & (freqs < 18000)
    assert np.allclose(20 * np.log10(np.abs(h[pick])), eq.response_db(band, freqs[pick], SR), atol=1e-6)


def _fl_window(label):
    data = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    window = next(w for w in data["windows"] if w["label"] == label)
    return np.array(data["freqs_hz"]), np.array(window["H_db"][0])


@pytest.mark.parametrize(("label", "freq"), [("peak +12 @100", 100), ("peak +12 @8k", 8000)])
def test_matches_fl_with_one_q_at_low_and_high_frequencies(label, freq):
    """FL's default width (39%) measured as Q 0.667 at 1 kHz; the same Q must fit at 100 Hz and 8 kHz."""
    freqs, fl = _fl_window(label)
    assert np.abs(eq.response_db([("peaking", freq, 12, 0.667)], freqs, SR) - fl).max() < 0.4


def test_matches_fls_resonant_highpass():
    freqs, fl = _fl_window("highpass @200 2")
    ours = eq.response_db([("highpass", 200, 0, 1.70)], freqs, SR)
    assert np.abs(ours - fl)[fl > -40].max() < 0.35
