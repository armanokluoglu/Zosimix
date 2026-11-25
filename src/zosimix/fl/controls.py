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

from zosimix.fl.bridge import Bridge

PROBE = Path(__file__).resolve().parents[3] / "fl_bridge" / "calibration" / "probe.json"

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

    The probe table gets within a few hundredths of a dB. Bisection against FL's own dB
    readout then closes the gap; it always converges because the fader only ever rises.
    """
    guess = fader_pos(db)
    lo, hi = max(guess - 0.01, 0.0), min(guess + 0.01, 1.0)
    pos, got = guess, math.nan
    for _ in range(25):
        fl.set_and_confirm("set_volume", "get_volume", track, pos)
        got = float(fl.call("get_volume_db", track)[0])
        if abs(got - db) <= tol_db:
            break
        lo, hi = (pos, hi) if got < db else (lo, pos)
        pos = (lo + hi) / 2
    return got
