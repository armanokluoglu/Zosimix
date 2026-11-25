"""The FL engine's mapping from mix state to FL controls (D63). Runs without FL: a fake
bridge records every command, and the measured calibration tables are checked directly."""

import json

import numpy as np
import pytest

from zosimix.engines import fl as fl_engine
from zosimix.fl import controls
from zosimix.mixstate import MixState, TrackState


def test_width_for_q_reproduces_the_measured_table():
    table = json.loads(controls.MAPPING.read_text(encoding="utf-8"))["q_by_width"]["peaking"]
    for width, q in table:
        assert controls.eq_width_pos("peaking", q) == pytest.approx(width, abs=1e-6)


def test_the_fault_qs_are_inside_what_fl_can_make():
    """Resonance faults use Q 8 and mud Q 1; FL must be able to cut both exactly."""
    assert 0.0 < controls.eq_width_pos("peaking", 8.0) < 0.05
    assert 0.2 < controls.eq_width_pos("peaking", 1.0) < 0.3


def test_q_beyond_fl_is_refused():
    with pytest.raises(ValueError):
        controls.eq_width_pos("peaking", 30.0)
    with pytest.raises(ValueError):
        controls.eq_width_pos("low_shelf", 3.0)          # FL has no resonant shelves


def test_mix_state_only_allows_qs_fl_can_make():
    with pytest.raises(ValueError):
        MixState.from_dict({"vox": {"eq": [{"type": "high_shelf", "freq_hz": 8000, "gain_db": 3, "q": 2.0}]}})
    with pytest.raises(ValueError):
        MixState.from_dict({"vox": {"eq": [{"type": "peaking", "freq_hz": 3000, "gain_db": -6, "q": 18}]}})
    MixState.from_dict({"vox": {"eq": [{"type": "peaking", "freq_hz": 3000, "gain_db": -6, "q": 8}]}})


@pytest.mark.parametrize("width", [0.0, 0.3, 0.7, 1.0, 1.25, 1.6, 2.0])
def test_separation_step_lands_close_to_any_width(width):
    sep, got = controls.sep_for_width(width)
    assert -1.0 <= sep <= 1.0 and abs(round(sep * 64) - sep * 64) < 1e-9     # a real 1/64 step
    assert got == pytest.approx(width, abs=0.009)
    if width == 1.0:
        assert sep == 0.0


def test_unity_gain_is_the_measured_constant():
    assert controls.unity_gain() == pytest.approx(0.99984, abs=1e-5)


class RecordingBridge:
    """Pretends to be FL: holds every value it's given, reports the fader as set in dB."""

    def __init__(self, fader_step_db: float = 0.0014):
        self.calls, self.values, self.step = [], {}, fader_step_db

    def call(self, command, *args):
        self.calls.append((command, *args))
        if command == "set_param":
            insert, _slot, param, pos = args
            self.values[("param", insert, param)] = pos
            return [repr(pos)]
        if command == "get_volume_db":
            return [repr(self.values[("fader", args[0])])]
        return ["ok"]

    def set_and_confirm(self, setter, getter, target, value, **_):
        self.calls.append((setter, target, value))
        if setter == "set_volume":
            # map position -> dB with the real table, then snap like FL's fader does
            dbs, positions = controls._fader_table()
            db = float(np.interp(value, positions, dbs))
            self.values[("fader", target)] = round(db / self.step) * self.step
        return value


def test_gain_beyond_the_fader_goes_on_the_main_level_exactly():
    fl = RecordingBridge()
    fl_engine.apply_track(fl, 3, "vox", TrackState(gain_db=8.0))
    fader = fl.values[("fader", 3)]
    main_db = (fl.values[("param", 3, controls.MAIN_LEVEL)] - 0.5) * 36
    assert fader <= controls.FADER_MAX_DB + 0.01
    assert fader + main_db == pytest.approx(8.0, abs=1e-9)            # the total is exact


def test_pan_goes_on_the_channel_rack_and_unused_bands_are_disabled():
    fl = RecordingBridge()
    state = TrackState(pan=-0.4, eq=MixState.from_dict(
        {"v": {"eq": [{"type": "highpass", "freq_hz": 100}]}}).tracks["v"].eq)
    fl_engine.apply_track(fl, 5, "vox", state)
    assert ("set_chan_pan", 4, -0.4) in fl.calls                     # channel k-1 plays slot k
    assert not [c for c in fl.calls if c[0] == "set_pan"]            # the mixer pan is never used
    types = {p: fl.values[("param", 5, controls.type_param(p))] for p in range(1, 8)}
    assert types[1] == pytest.approx(controls.eq_type_pos("highpass"))
    assert all(types[p] == controls.eq_type_pos("disabled") for p in range(2, 8))
