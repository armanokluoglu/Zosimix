"""FL's knob positions <-> real units, from the probe (D57).

FL's API takes normalized 0..1 positions. These helpers convert to and from the units
FL itself reports (dB, Hz, named choices). What those units *do to the sound* is a
separate question, answered by the audio calibration (zosimix.fl.calibrate).
"""

from __future__ import annotations

import json
import math
from functools import cache
from pathlib import Path

import numpy as np

from zosimix.fl.bridge import Bridge, BridgeError

PROBE = Path(__file__).resolve().parents[3] / "fl_bridge" / "calibration" / "probe.json"
MAPPING = PROBE.parent / "mapping.json"     # width->Q and separation->width tables (D63)

FADER_MAX_DB = 5.59             # position 1.0; boost beyond this goes on PEQ2's main level (D43)
EQ_SLOT = 0                     # PEQ2 sits in the first effect slot of every insert
EQ_LEVEL_RANGE_DB = 18.0        # PEQ2 levels run -18..+18 dB, linear in position
EQ_TYPES = ("disabled", "lowpass", "bandpass", "highpass", "notch", "low_shelf", "peaking", "high_shelf")
EQ_ORDERS = ("steep8", "steep6", "steep4", "2", "gentle4", "gentle6", "gentle8")
MAIN_LEVEL = 35                 # PEQ2 parameter index of the main (output) level


# PEQ2 parameter indices for band b = 1..7 (probe.json lists all 36).
def level_param(band: int) -> int:
    return band - 1


def freq_param(band: int) -> int:
    return 7 + band - 1


def width_param(band: int) -> int:
    return 14 + band - 1


def type_param(band: int) -> int:
    return 21 + band - 1


def order_param(band: int) -> int:
    return 28 + band - 1


def eq_level_pos(db: float) -> float:
    return 0.5 + db / (2 * EQ_LEVEL_RANGE_DB)


def eq_freq_pos(hz: float) -> float:
    """FL shows Hz = 20 * 1000^x, so x = log(hz / 20) / log(1000)."""
    return math.log(hz / 20.0) / math.log(1000.0)


def eq_type_pos(name: str) -> float:
    return EQ_TYPES.index(name) / (len(EQ_TYPES) - 1)


def eq_order_pos(name: str) -> float:
    return EQ_ORDERS.index(name) / (len(EQ_ORDERS) - 1)


@cache
def _mapping() -> dict:
    return json.loads(MAPPING.read_text(encoding="utf-8"))


# Which measured width->Q table serves each mix-state band type (D63).
Q_TABLE = {"peaking": "peaking", "low_shelf": "shelf", "high_shelf": "shelf",
           "highpass": "highpass", "lowpass": "lowpass"}


def eq_width_pos(type_: str, q: float) -> float:
    """PEQ2's width knob position that gives this Q, from the measured table (D63).

    Q falls as the width rises, roughly evenly in log(Q), so we interpolate the width
    against log(Q). A Q just outside the measured range (by up to 5%) is clamped to the
    nearest end; anything further is outside what FL can do and raises.
    """
    rows = np.array(_mapping()["q_by_width"][Q_TABLE[type_]])        # [[width, q], ...], q falling
    widths, log_qs = rows[:, 0], np.log(rows[:, 1])
    log_q = math.log(q)
    if not log_qs.min() - 0.05 <= log_q <= log_qs.max() + 0.05:
        raise ValueError(f"{type_} q={q} is outside what FL's Parametric EQ 2 can make "
                         f"({rows[:, 1].min():.2f}..{rows[:, 1].max():.2f})")
    return float(np.interp(log_q, log_qs[::-1], widths[::-1]))


def unity_gain() -> float:
    """What a fully neutral path through FL passes (0.99984, D63); the FL engine divides it out."""
    return float(_mapping()["unity_gain"])


def sep_for_width(width: float) -> tuple[float, float]:
    """(stereo separation, the width it actually gives): the 1/64 step closest to `width`.

    Separation moves in steps, so most widths are matched to within about 0.008 (D63).
    """
    rows = np.array(_mapping()["width_by_sep"])                        # [[sep, width], ...]
    i = int(np.argmin(np.abs(rows[:, 1] - width)))
    return float(rows[i, 0]), float(rows[i, 1])


@cache
def _fader_table() -> tuple[np.ndarray, np.ndarray]:
    """(dB, position) pairs FL reported for the fader, skipping position 0 (-inf dB)."""
    rows = json.loads(PROBE.read_text(encoding="utf-8"))["volume"][1:]
    return np.array([float(r[2]) for r in rows]), np.array([r[0] for r in rows])


def fader_pos(db: float) -> float:
    """A first guess at the fader position for `db`, interpolated from the probe table."""
    dbs, positions = _fader_table()
    if db > FADER_MAX_DB + 1e-6:
        raise ValueError(f"the fader tops out at +{FADER_MAX_DB} dB, asked for {db}")
    return float(np.interp(db, dbs, positions))


def set_fader_db(fl: Bridge, track: int, db: float, tol_db: float = 0.005) -> float:
    """Set a fader to `db` as FL itself reports it. Returns the dB FL reports at the end.

    The probe table's guess is usually within a few hundredths of a dB. From there,
    bisection over the fader's whole travel (0..1) closes the gap against FL's own dB
    readout. It always converges because the fader only ever rises, from -inf dB at 0.
    The whole travel matters: the table stops at -42 dB, the mix state goes down to -60.
    """
    lo, hi = 0.0, 1.0
    pos, got = fader_pos(db), math.nan
    for _ in range(40):
        fl.set_and_confirm("set_volume", "get_volume", track, pos)
        got = float(fl.call("get_volume_db", track)[0])
        if abs(got - db) <= tol_db:
            return got
        lo, hi = (pos, hi) if got < db else (lo, pos)
        pos = (lo + hi) / 2
    raise BridgeError(f"fader {track} didn't reach {db} dB; FL reports {got} dB")
