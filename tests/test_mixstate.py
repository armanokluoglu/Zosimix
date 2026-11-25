"""MixState validation: anything outside the action space is rejected with a readable message."""

from __future__ import annotations

import math

import pytest

from zosimix.mixstate import EqBand, MixState


def test_round_trip_keeps_every_setting():
    data = {"vox": {"gain_db": -3.0, "pan": 0.2, "polarity": True, "width": 1.5,
                    "eq": [{"type": "peaking", "freq_hz": 2000.0, "gain_db": -6.0, "q": 4.0}]}}
    assert MixState.from_dict(data).to_dict() == data


@pytest.mark.parametrize("data, message", [
    ({"vox": {"pan": 1.4}}, "outside the allowed range"),
    ({"vox": {"gain_db": math.nan}}, "outside the allowed range"),
    ({"vox": {"gain_db": True}}, "not a number"),
    ({"vox": {"polarity": "false"}}, "true or false"),
    ({"vox": {"eq": [{"type": "notch"}]}}, "allowed"),
    ({"vox": {"eq": [{}] * 8}}, "maximum"),
    ([], "must be an object"),
])
def test_invalid_states_are_rejected(data, message):
    with pytest.raises((ValueError, TypeError), match=message):
        MixState.from_dict(data)


def test_q_defaults_to_no_bump_for_highpass_and_lowpass():
    """D62: leaving q out of a highpass/lowpass must not add a resonance at the cutoff."""
    state = MixState.from_dict({"vox": {"eq": [{"type": "highpass", "freq_hz": 80},
                                               {"type": "lowpass", "freq_hz": 12000},
                                               {"type": "peaking", "freq_hz": 300, "gain_db": -3}]}})
    qs = [b.q for b in state.tracks["vox"].eq]
    assert qs == [pytest.approx(0.7071, abs=1e-4), pytest.approx(0.7071, abs=1e-4), 1.0]
    assert EqBand("highpass", 80, 0, 2.0).q == 2.0          # an explicit q is kept
