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
from scipy.optimize import minimize_scalar
from scipy.signal import csd, welch

from zosimix import eq as eq_filters
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


def fitted(type_: str, freq: float, gain_db: float, width: float, table: str | None = None) -> dict:
    """A single-band EQ setting whose Q gets fitted (D63). `table` names the width->Q table
    it belongs to; settings without one only check that the table holds at other gains."""
    window = {"label": f"{type_} {gain_db:+g} @{freq:g} w{width}", "params": eq(type_, freq, gain_db, width),
              "fit": {"type": type_, "freq": freq, "gain_db": gain_db, "width": width}}
    if table:
        window["fit"]["table"] = table
    return window


# Widths for the width->Q tables: dense where Q changes fastest (narrow bands).
PEAK_WIDTHS = (0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.065, 0.08, 0.1, 0.125, 0.15, 0.2, 0.25,
               0.3, DEFAULT_WIDTH, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
SHELF_WIDTHS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, DEFAULT_WIDTH, 0.45, 0.5, 0.55, 0.6122, 0.65, 0.7,
                0.75, 0.8, 0.85, 0.9, 1.0)
PASS_WIDTHS = (0.0, 0.05, 0.1, 0.2, 0.3, DEFAULT_WIDTH, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def _sep_steps(first: int, last: int) -> list[dict]:
    """Stereo separation moves in steps of 1/64. The positive half is a curve, so measure every step."""
    return [{"label": f"sep {k}/64", "sep": k / 64} for k in range(first, last + 1)]


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
    # Dense tables for the FL engine (D63). Narrow peaks are measured at 2 kHz, where even
    # the narrowest band spans many analysis bins.
    "peak_widths": [fitted("peaking", 2000, 12, w, "peaking") for w in PEAK_WIDTHS],
    "shelf_widths": [
        *(fitted("low_shelf", 200, 6, w, "shelf") for w in SHELF_WIDTHS),
        fitted("low_shelf", 200, -12, DEFAULT_WIDTH), fitted("low_shelf", 200, 12, 0.8),
        fitted("high_shelf", 4000, 6, 0.1), fitted("high_shelf", 4000, -9, 0.8),
    ],
    "pass_widths": [
        *(fitted("highpass", 200, 0, w, "highpass") for w in PASS_WIDTHS),
        *(fitted("lowpass", 2000, 0, w, "lowpass") for w in PASS_WIDTHS),
    ],
    "sep_1": _sep_steps(1, 21),
    "sep_2": _sep_steps(22, 42),
    "sep_3": _sep_steps(43, 63),
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


def response(x: np.ndarray, y: np.ndarray, ch: int) -> tuple[np.ndarray, np.ndarray]:
    """Full-resolution magnitude response of one channel in dB (5.4 Hz bins)."""
    f, pxx = welch(x[:, ch], SR, nperseg=8192)
    _, pxy = csd(x[:, ch], y[:, ch], SR, nperseg=8192)
    return f, 20 * np.log10(np.abs(pxy) / pxx + 1e-12)


def measure(x: np.ndarray, y: np.ndarray) -> dict:
    """Compare one window's output y with its input x (both (frames, 2))."""
    m, *_ = np.linalg.lstsq(x, y, rcond=None)                 # y ~= x @ m
    resid = y - x @ m
    h_db = []
    for ch in range(2):
        f, mag_db = response(x, y, ch)
        h_db.append(np.round(np.interp(FREQS, f, mag_db), 3).tolist())
    return {"M": np.round(m, 6).tolist(),
            "matrix_residual_db": round(10 * np.log10((resid ** 2).sum() / max((y ** 2).sum(), 1e-20)), 2),
            "H_db": h_db}


def fit_q(f: np.ndarray, measured_db: np.ndarray, type_: str, freq: float, gain_db: float) -> dict:
    """The Q that makes zosimix.eq's filter best match FL's measured response (D63).

    Compared from 20 Hz to 20 kHz, wherever the filter passes sound (above -40 dB). The
    error is RMS in dB, which is smooth in Q, so a bounded 1-D search finds the minimum.
    """
    use = (f >= 20) & (f <= 20000) & (measured_db > -40)
    f, measured_db = f[use], measured_db[use]

    def rms_error(log_q: float) -> float:
        diff = eq_filters.response_db([(type_, freq, gain_db, 10 ** log_q)], f, SR) - measured_db
        return float(np.sqrt(np.mean(diff ** 2)))

    best = minimize_scalar(rms_error, bounds=(np.log10(0.03), np.log10(300)), method="bounded",
                           options={"xatol": 1e-5})
    q = float(10 ** best.x)
    diff = eq_filters.response_db([(type_, freq, gain_db, q)], f, SR) - measured_db
    return {"q": round(q, 5), "rms_err_db": round(best.fun, 4), "max_err_db": round(float(np.abs(diff).max()), 4)}


def side_gain(m: list[list[float]]) -> dict:
    """Stereo separation as mid/side scaling: width = how much side signal survives (1 = unchanged)."""
    return {"width": round(m[0][0] - m[0][1], 5), "mid_gain": round(m[0][0] + m[0][1], 5)}


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
        window = {"label": st["label"], "setting": {k2: v for k2, v in st.items() if k2 != "label"},
                  "reported": reported[k], **measure(x, seg)}
        if "fit" in st:
            fit = st["fit"]
            window["fit"] = {**fit, **fit_q(*response(x, seg, 0), fit["type"], fit["freq"], fit["gain_db"])}
        if "sep" in st:
            window["stereo"] = side_gain(window["M"])
        results.append(window)
    return {"render": name, "seconds": round(time.monotonic() - t0, 1), "level_rms": LEVEL,
            "freqs_hz": np.round(FREQS, 3).tolist(), "windows": results}


def build_mapping() -> dict:
    """Collect the dense measurements into the tables the FL engine uses (mapping.json, D63).

    q_by_width: {table: [[width, q], ...]} for peaking, shelf, highpass and lowpass.
    width_by_sep: [[sep, width], ...] for every 1/64 step of stereo separation. The negative
                  half is width = 1 - sep exactly (D60); the positive half is measured.
    """
    tables: dict[str, list[list[float]]] = {}
    seps = {0.0: 1.0, 1.0: 0.0}
    for path in sorted(OUT_DIR.glob("audio-*.json")):
        for w in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            fit = w.get("fit")
            if fit and fit.get("table"):
                tables.setdefault(fit["table"], []).append([fit["width"], fit["q"]])
            if "stereo" in w and w["setting"]["sep"] > 0:
                seps[round(w["setting"]["sep"] * 64) / 64] = w["stereo"]["width"]
    for k in range(1, 65):
        seps[-k / 64] = 1 + k / 64
    return {"q_by_width": {t: sorted(rows) for t, rows in tables.items()},
            "width_by_sep": sorted([s, w] for s, w in seps.items()),
            "unity_gain": unity_gain()}


def unity_gain() -> float:
    """What a fully neutral path through FL passes: 0.99984, not 1 (D63). Averaged over the
    neutral windows and the mid gain of every separation step, which all agree to 6 digits."""
    values = []
    for path in sorted(OUT_DIR.glob("audio-*.json")):
        for w in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            if w["label"].startswith("neutral"):
                values.append(w["M"][0][0])
            if "stereo" in w:
                values.append(w["stereo"]["mid_gain"])
    return round(float(np.mean(values)), 6)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render", choices=[*RENDERS, "table"], help="a render to measure, or 'table' to build mapping.json")
    name = ap.parse_args().render
    if name == "table":
        mapping = build_mapping()
        controls.MAPPING.write_text(json.dumps(mapping, indent=1), encoding="utf-8")
        print(f"wrote {controls.MAPPING}: {', '.join(f'{t} ({len(r)})' for t, r in mapping['q_by_width'].items())}, "
              f"{len(mapping['width_by_sep'])} separation steps")
        return
    result = run(name)
    out = OUT_DIR / f"audio-{name}.json"
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out} ({len(result['windows'])} settings, {result['seconds']} s)")


if __name__ == "__main__":
    main()
