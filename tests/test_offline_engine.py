"""Tests for the MixState and the offline engine.

The most important property: every *fixable* fault from zosimix.faults can be undone with
the agent's action space, bringing the render back to the clean mix. If that ever stops
being true, the benchmark would contain tasks that no agent could solve.
"""

from __future__ import annotations

import numpy as np
import pytest

from zosimix import audio, faults
from zosimix.engines.offline import OfflineEngine
from zosimix.mixstate import EqBand, MixState, TrackState

SR = 44100


@pytest.fixture
def stems():
    rng = np.random.default_rng(0)
    t = np.arange(SR * 2) / SR

    def tone(freqs):
        return (0.1 * sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) for f in freqs) / len(freqs))[:, None]

    return {
        "drums_kick": tone([60, 120]),
        "bass": tone([55, 110, 220]),
        "vox_lead": tone([220, 440, 880, 1760, 3520]),
        "guitar_wide": 0.05 * rng.standard_normal((SR * 2, 2)),
    }


def residual_db(a: np.ndarray, reference: np.ndarray) -> float:
    """How much is left after subtracting the reference, relative to the reference (dB)."""
    return audio.gain_to_db(audio.rms(a - reference) / audio.rms(reference))


def repaired(stems, fault: faults.Fault, fix: TrackState) -> float:
    broken = dict(stems)
    broken[fault.stem] = faults.apply(fault, stems[fault.stem], SR)
    engine = OfflineEngine(broken, SR)
    engine.set_state(MixState({fault.stem: fix}))
    return residual_db(engine.render(), audio.mix(stems))


def test_neutral_state_renders_the_clean_mix_exactly(stems):
    engine = OfflineEngine(stems, SR)
    np.testing.assert_allclose(engine.render(), audio.mix(stems))


def test_gain_fault_is_undone_by_the_opposite_gain(stems):
    fault = faults.Fault("gain", "vox_lead", 1, {"gain_db": -6.0})
    assert repaired(stems, fault, TrackState(gain_db=6.0)) < -100


def test_polarity_fault_is_undone_by_flipping_back(stems):
    fault = faults.Fault("polarity", "drums_kick", 0)
    assert repaired(stems, fault, TrackState(polarity=True)) < -100


@pytest.mark.parametrize("fault_type,freq,gain,q", [("resonance", 880.0, 8.0, 8.0), ("mud", 300.0, 6.0, 1.0)])
def test_eq_faults_are_undone_by_the_mirror_cut(stems, fault_type, freq, gain, q):
    fault = faults.Fault(fault_type, "vox_lead", 1, {"freq_hz": freq, "gain_db": gain, "q": q})
    fix = TrackState(eq=[EqBand("peaking", freq, -gain, q)])
    assert repaired(stems, fault, fix) < -40          # a cut mirrors a boost almost exactly


def test_pan_fault_is_undone_by_panning_back_and_restoring_level(stems):
    pan = 0.6
    fault = faults.Fault("pan", "vox_lead", 1, {"pan": pan})
    # Panning back with a balance control also lowers the level by cos(pan * pi/2),
    # so a complete fix pans back *and* raises the fader, as an engineer would in FL.
    level_db = -audio.gain_to_db(np.cos(pan * np.pi / 2))
    assert repaired(stems, fault, TrackState(pan=-pan, gain_db=level_db)) < -100


def test_width_zero_makes_a_track_mono(stems):
    engine = OfflineEngine(stems, SR)
    engine.set_state(MixState({"guitar_wide": TrackState(width=0.0)}))
    out = engine.render_stems()["guitar_wide"]
    np.testing.assert_allclose(out[:, 0], out[:, 1])


def test_pan_comes_before_width_like_in_fl(stems):
    """FL applies the channel-rack pan before the mixer's stereo separation (D61).

    Pan then width 0 gives a centred mono track (left == right). The other order would
    give a mono signal that is still panned (left != right).
    """
    engine = OfflineEngine(stems, SR)
    engine.set_state(MixState({"guitar_wide": TrackState(pan=0.5, width=0.0)}))
    out = engine.render_stems()["guitar_wide"]
    np.testing.assert_allclose(out[:, 0], out[:, 1])


def test_only_changed_tracks_are_re_rendered(stems):
    engine = OfflineEngine(stems, SR)
    engine.set_state(MixState({"bass": TrackState(gain_db=-3.0)}))
    first = engine.render_stems()
    engine.set_state(MixState({"bass": TrackState(gain_db=-3.0), "vox_lead": TrackState(gain_db=2.0)}))
    second = engine.render_stems()
    assert second["bass"] is first["bass"]                    # reused from the cache
    assert second["vox_lead"] is not first["vox_lead"]        # re-rendered


def test_out_of_range_and_unknown_stems_are_rejected(stems):
    engine = OfflineEngine(stems, SR)
    with pytest.raises(ValueError, match="gain_db"):
        engine.set_state(MixState({"bass": TrackState(gain_db=30.0)}))
    with pytest.raises(ValueError, match="unknown stems"):
        engine.set_state(MixState({"tuba": TrackState()}))
    with pytest.raises(ValueError, match="type"):
        engine.set_state(MixState({"bass": TrackState(eq=[EqBand(type="notch")])}))


def test_mix_state_survives_a_json_round_trip():
    state = MixState({"bass": TrackState(gain_db=-2.5, pan=0.1, eq=[EqBand("low_shelf", 120.0, -3.0, 0.7)])})
    assert MixState.from_dict(state.to_dict()) == state
