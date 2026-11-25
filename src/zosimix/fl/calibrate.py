"""Audio calibration: what FL's controls actually do to the sound (D60).

The probe (D57) tells us what FL *says* each knob position means. This measures what the
knobs *do*, by rendering test signals through FL:

  - Slot k plays its own burst of stereo noise, in time window k only. Insert k gets
    setting k. So in the master render, window k holds insert k's output and nothing else,
    and one render measures 24 settings.
  - For each window we compare the output with the input:
      M      a 2x2 matrix with out = in @ M. M[i][j] is how much of input channel i
             reaches output channel j. Gain, pan, stereo width and polarity show up here.
      H_db   the magnitude response of each output channel, at 241 log-spaced
             frequencies from 20 Hz to 20 kHz. EQ shows up here.

Results (measurements only, no audio) go to fl_bridge/calibration/audio-<render>.json. The
renders themselves stay in C:\\zosimix\\fl\\work.

Usage:
    python -m zosimix.fl.calibrate mixer      # fader, pan, separation, polarity, peak widths
    python -m zosimix.fl.calibrate pan        # channel-rack pan, more separation and pan points
    python -m zosimix.fl.calibrate eq         # EQ shapes: peaks, shelves, high/low-pass slopes
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import csd, welch

from zosimix.fl import controls, session, slots
from zosimix.fl.bridge import Bridge

OUT_DIR = Path(__file__).resolve().parents[3] / "fl_bridge" / "calibration"
SR = slots.SR
BURST_S, GAP_S = 2.0, 0.5           # the gap lets EQ ringing die out before the next window
LEVEL = 0.02                        # noise RMS (-34 dBFS): +18 dB of boost still can't clip
FREQS = np.geomspace(20.0, 20000.0, 241)
BAND = 4                            # the PEQ2 band used for single-band EQ tests
DEFAULT_WIDTH = 0.3878              # PEQ2's default width for bands 2-6 (probe.json)


def eq(type_: str, freq: float, gain_db: float = 0.0, width: float = DEFAULT_WIDTH, order: str = "2") -> dict:
    """PEQ2 parameter positions that turn band BAND into one filter."""
    b = BAND
    return {controls.type_param(b): controls.eq_type_pos(type_),
            controls.freq_param(b): controls.eq_freq_pos(freq),
            controls.level_param(b): controls.eq_level_pos(gain_db),
            controls.width_param(b): width,
            controls.order_param(b): controls.eq_order_pos(order)}


def _peak_widths() -> list[dict]:
    return [{"label": f"peak +12 @1k w{w}", "params": eq("peaking", 1000, 12, w)}
            for w in (0.05, 0.1, 0.2, 0.3, DEFAULT_WIDTH, 0.5, 0.7, 1.0)]


RENDERS: dict[str, list[dict]] = {
    "mixer": [
        {"label": "neutral A"},
        {"label": "neutral B"},
        {"label": "fader -12", "fader_db": -12.0},
        {"label": "fader +3", "fader_db": 3.0},
        {"label": "fader max", "fader_db": controls.FADER_MAX_DB},
        {"label": "main level +6", "params": {controls.MAIN_LEVEL: controls.eq_level_pos(6.0)}},
        *({"label": f"pan {p:+}", "pan": p} for p in (-1.0, -0.5, -0.25, 0.5, 1.0)),
        *({"label": f"sep {s:+}", "sep": s} for s in (-1.0, -0.5, 0.5, 1.0)),
        {"label": "polarity", "polarity": True},
        *_peak_widths(),
    ],
    "pan": [
        {"label": "neutral"},
        *({"label": f"channel pan {p:+}", "chan_pan": p} for p in (-1.0, -0.75, -0.5, -0.25, 0.25, 0.5, 1.0)),
        *({"label": f"sep {s:+}", "sep": s} for s in (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, -0.25, -0.75)),
        *({"label": f"pan {p:+}", "pan": p} for p in (-0.75, -0.1, 0.25, 0.75)),
    ],
    "eq": [
        {"label": "peak -12 @1k w0.2", "params": eq("peaking", 1000, -12, 0.2)},
        {"label": "peak -12 @1k w0.5", "params": eq("peaking", 1000, -12, 0.5)},
        {"label": "peak +12 @100", "params": eq("peaking", 100, 12)},
        {"label": "peak +12 @8k", "params": eq("peaking", 8000, 12)},
        {"label": "peak +6 @1k", "params": eq("peaking", 1000, 6)},
        {"label": "peak +18 @1k", "params": eq("peaking", 1000, 18)},
        *({"label": f"low shelf +6 @200 w{w}", "params": eq("low_shelf", 200, 6, w)} for w in (0.2, DEFAULT_WIDTH, 0.6122, 1.0)),
        *({"label": f"high shelf +6 @4k w{w}", "params": eq("high_shelf", 4000, 6, w)} for w in (0.2, DEFAULT_WIDTH, 0.6122, 1.0)),
        *({"label": f"highpass @200 {o}", "params": eq("highpass", 200, order=o)} for o in controls.EQ_ORDERS),
        {"label": "highpass @200 2 w0.2", "params": eq("highpass", 200, width=0.2)},
        {"label": "highpass @200 2 w0.7", "params": eq("highpass", 200, width=0.7)},
        {"label": "lowpass @2k 2", "params": eq("lowpass", 2000)},
    ],
}


def windows(n: int) -> list[tuple[int, int]]:
    """(start, stop) sample ranges: burst plus the gap after it, one per slot."""
    step = int((BURST_S + GAP_S) * SR)
    return [(k * step, (k + 1) * step) for k in range(n)]


def test_signals(n: int, seed: int = 0) -> dict[str, np.ndarray]:
    """Slot k: independent stereo white noise in window k, silence elsewhere."""
    rng = np.random.default_rng(seed)
    wins = windows(n)
    total = wins[-1][1]
    stems = {}
    for k, (start, _) in enumerate(wins):
        x = np.zeros((total, 2), np.float32)
        x[start:start + int(BURST_S * SR)] = rng.standard_normal((int(BURST_S * SR), 2)) * LEVEL
        stems[f"cal{k + 1:02d}"] = x
    return stems


def apply(fl: Bridge, track: int, setting: dict) -> dict:
    """Put one setting on one insert. Returns what FL reports afterwards."""
    reported = {}
    if "fader_db" in setting:
        reported["fader_db"] = controls.set_fader_db(fl, track, setting["fader_db"])
    if "pan" in setting:
        reported["pan"] = fl.set_and_confirm("set_pan", "get_pan", track, setting["pan"])
    if "chan_pan" in setting:
        channel = track - 1                       # template: channel k-1 plays slot k
        reported["chan_name"] = fl.call("chan_name", channel)[0]
        reported["chan_pan"] = fl.set_and_confirm("set_chan_pan", "get_chan_pan", channel, setting["chan_pan"])
    if "sep" in setting:
        reported["sep"] = fl.set_and_confirm("set_sep", "get_sep", track, setting["sep"], tol=0.02)
    if setting.get("polarity"):
        fl.call("set_polarity", track, 1)
        reported["polarity"] = fl.call("get_polarity", track)[0]
    shown = {}
    for p, pos in setting.get("params", {}).items():
        fl.call("set_param", track, controls.EQ_SLOT, p, pos)
        name, _, text = fl.call("param_info", track, controls.EQ_SLOT, p)
        shown[name] = text
    if shown:
        reported["params"] = shown
    return reported


def measure(x: np.ndarray, y: np.ndarray) -> dict:
    """Compare one window's output y with its input x (both (frames, 2))."""
    m, *_ = np.linalg.lstsq(x, y, rcond=None)                 # y ~= x @ m
    resid = y - x @ m
    h_db = []
    for ch in range(2):
        f, pxx = welch(x[:, ch], SR, nperseg=8192)
        _, pxy = csd(x[:, ch], y[:, ch], SR, nperseg=8192)
        mag = np.abs(pxy) / pxx
        h_db.append(np.round(20 * np.log10(np.interp(FREQS, f, mag) + 1e-12), 3).tolist())
    return {"M": np.round(m, 6).tolist(),
            "matrix_residual_db": round(10 * np.log10((resid ** 2).sum() / max((y ** 2).sum(), 1e-20)), 2),
            "H_db": h_db}


def run(name: str) -> dict:
    settings = RENDERS[name]
    stems = test_signals(len(settings))
    slots.write_song(stems, SR)
    project = session.new_project(f"cal_{name}")
    t0 = time.monotonic()
    with session.FLSession(project) as s:
        reported = [apply(s.fl, k + 1, st) for k, st in enumerate(settings)]
        s.save()
    wav = session.render(project, min_seconds=windows(len(settings))[-1][1] / SR)
    y, sr = sf.read(wav, always_2d=True)
    if sr != SR:
        raise ValueError(f"render came back at {sr} Hz")
    results = []
    for k, ((start, stop), st) in enumerate(zip(windows(len(settings)), settings, strict=True)):
        x = stems[f"cal{k + 1:02d}"][start:stop].astype(np.float64)
        seg = np.zeros_like(x)
        got = y[start:min(stop, len(y))]
        seg[:len(got)] = got
        results.append({"label": st["label"], "setting": {k2: v for k2, v in st.items() if k2 != "label"},
                        "reported": reported[k], **measure(x, seg)})
    return {"render": name, "seconds": round(time.monotonic() - t0, 1), "level_rms": LEVEL,
            "freqs_hz": np.round(FREQS, 3).tolist(), "windows": results}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render", choices=list(RENDERS))
    name = ap.parse_args().render
    result = run(name)
    out = OUT_DIR / f"audio-{name}.json"
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out} ({len(result['windows'])} settings, {result['seconds']} s)")


if __name__ == "__main__":
    main()
