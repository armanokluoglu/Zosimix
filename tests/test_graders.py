"""Tests for the graders: a perfect answer passes, lazy or wrong answers fail.

Graders are the most interview-probed code in the project, so each rule gets its own test.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from zosimix import audio, faults, graders
from zosimix.mixstate import EqBand, MixState, TrackState
from zosimix.tasks import TaskSpec

SR = 44100


@pytest.fixture
def songs_root(tmp_path):
    rng = np.random.default_rng(0)
    t = np.arange(SR * 3) / SR
    kick = 0.3 * np.sin(2 * np.pi * 55 * t) * (np.sin(2 * np.pi * 2 * t) > 0)
    room = 0.2 * np.sin(2 * np.pi * 70 * t)      # what both overhead mics pick up; unrelated to the kick mic
    stems = {
        "drums_kick": kick[:, None],
        "drums_overheads_1": (0.5 * room + 0.01 * rng.standard_normal(len(t)))[:, None],
        "drums_overheads_2": (0.5 * room + 0.01 * rng.standard_normal(len(t)))[:, None],
        "bass": (0.2 * np.sin(2 * np.pi * 82 * t))[:, None],
        "vox_lead": (0.05 * rng.standard_normal(len(t)))[:, None],
    }
    folder = tmp_path / "songs" / "synthetic"
    for name, a in stems.items():
        audio.write(folder / "stems" / f"{name}.wav", a, SR)
    (folder / "song.json").write_text(json.dumps({"song_id": "synthetic"}), encoding="utf-8")
    return tmp_path / "songs"


def spec(fault: faults.Fault) -> TaskSpec:
    return TaskSpec("t-001", "synthetic", fault.to_dict(), "none", "")


def answer(verdict, stem=None, fault_type=None):
    return {"verdict": verdict, "findings": [{"stem": stem, "fault_type": fault_type}] if stem else []}


GAIN = faults.Fault("gain", "vox_lead", 1, {"gain_db": 6.0})


def test_perfect_gain_repair_passes(songs_root):
    state = MixState({"vox_lead": TrackState(gain_db=-6.0)}).to_dict()
    r = graders.grade(spec(GAIN), answer("fixed", "vox_lead", "gain"), state, songs_root)
    assert r["pass"] and r["repair"]["score"] == pytest.approx(1.0)


def test_right_diagnosis_without_a_fix_fails(songs_root):
    r = graders.grade(spec(GAIN), answer("fixed", "vox_lead", "gain"), {}, songs_root)
    assert r["detected"] and not r["pass"] and r["repair"]["score"] == pytest.approx(0.0)


def test_fixing_by_turning_everything_else_up_counts_as_collateral(songs_root):
    state = {n: {"gain_db": 6.0} for n in ["drums_kick", "drums_overheads_1", "drums_overheads_2", "bass"]}
    r = graders.grade(spec(GAIN), answer("fixed", "vox_lead", "gain"), state, songs_root)
    assert not r["pass"] and len(r["touched_other_stems"]) == 4


def test_wrong_stem_is_not_detected(songs_root):
    state = MixState({"vox_lead": TrackState(gain_db=-6.0)}).to_dict()
    r = graders.grade(spec(GAIN), answer("fixed", "bass", "gain"), state, songs_root)
    assert not r["detected"] and not r["pass"]


def test_resonance_mirror_cut_passes(songs_root):
    fault = faults.Fault("resonance", "vox_lead", 2, {"freq_hz": 2000.0, "gain_db": 12.0, "q": 8.0})
    state = MixState({"vox_lead": TrackState(eq=[EqBand("peaking", 2000.0, -12.0, 8.0)])}).to_dict()
    r = graders.grade(spec(fault), answer("fixed", "vox_lead", "resonance"), state, songs_root)
    assert r["pass"] and r["repair"]["score"] > 0.9


def test_polarity_accepts_flipping_either_mic_of_the_pair(songs_root):
    fault = faults.Fault("polarity", "drums_overheads_2", 0)
    state = MixState({"drums_overheads_1": TrackState(polarity=True)}).to_dict()
    r = graders.grade(spec(fault), answer("fixed", "drums_overheads_1", "polarity"), state, songs_root)
    assert r["detected"]
    assert r["repair"]["score"] > 0.5            # low end largely restored either way


def test_clipping_must_be_reported_and_left_alone(songs_root):
    fault = faults.Fault("clipping", "vox_lead", 1, {"depth_db": 12.0})
    ok = graders.grade(spec(fault), answer("unfixable", "vox_lead", "clipping"), {}, songs_root)
    assert ok["pass"]
    faked = graders.grade(spec(fault), answer("fixed", "vox_lead", "clipping"),
                          {"vox_lead": {"gain_db": -3.0}}, songs_root)
    assert not faked["pass"]


def test_control_passes_only_if_nothing_is_reported_or_changed(songs_root):
    control = faults.Fault("control", None, 0)
    assert graders.grade(spec(control), answer("no_fault"), {}, songs_root)["pass"]
    assert not graders.grade(spec(control), answer("fixed", "bass", "gain"),
                             {"bass": {"gain_db": -2.0}}, songs_root)["pass"]


def test_missing_submission_fails(songs_root):
    r = graders.grade(spec(GAIN), None, None, songs_root)
    assert r == {**r, "submitted": False, "pass": False}


def test_polarity_only_accepts_stems_whose_flip_restores_low_end(songs_root):
    fault = faults.Fault("polarity", "drums_overheads_2", 0)
    r = graders.grade(spec(fault), answer("fixed", "drums_kick", "polarity"),
                      {"drums_kick": {"polarity": True}}, songs_root)
    assert not r["detected"]                      # flipping the unrelated kick mic fixes nothing


@pytest.mark.parametrize("bad_state", [
    ["vox_lead", -6.0],                              # a list instead of an object
    {"vox_lead": None},                              # settings missing
    {"vox_lead": {"gain_db": "-6"}},                 # a number written as a string
    {"vox_lead": {"eq": "cut 2k"}},                  # eq not a list of bands
    {"vox_lead": {"volume": -6.0}},                  # unknown setting
])
def test_malformed_mix_state_is_graded_as_no_changes(songs_root, bad_state):
    r = graders.grade(spec(GAIN), answer("fixed", "vox_lead", "gain"), bad_state, songs_root)
    assert r["invalid_mix_state"] and not r["pass"] and r["repair"]["score"] == pytest.approx(0.0)


@pytest.mark.parametrize("bad_diagnosis", [
    ["fixed"],                                       # a list instead of an object
    {"verdict": "fixed", "findings": {"stem": "vox_lead", "fault_type": "gain"}},   # one finding, not a list
    {"verdict": "fixed", "findings": ["vox_lead gain"]},                            # finding as plain text
    {"verdict": ["fixed"], "findings": [{"stem": ["vox_lead"], "fault_type": "gain"}]},
])
def test_malformed_diagnosis_is_graded_not_crashed(songs_root, bad_diagnosis):
    state = MixState({"vox_lead": TrackState(gain_db=-6.0)}).to_dict()
    r = graders.grade(spec(GAIN), bad_diagnosis, state, songs_root)
    assert r["submitted"] and not r["detected"] and not r["pass"]


def test_badly_formatted_false_alarm_still_fails_a_control(songs_root):
    control = faults.Fault("control", None, 0)
    r = graders.grade(spec(control), {"verdict": "no_fault", "findings": ["bass seems loud"]}, {}, songs_root)
    assert r["invalid_diagnosis"] and not r["pass"]


def _group_renders(spec_, mix_state, songs_root):
    """What FL's group renders would be, made with the offline engine: each group's processed
    stems summed, everything else muted (D70)."""
    from zosimix.engines.offline import OfflineEngine
    from zosimix.songs import list_songs
    stems, sr, _ = list_songs(songs_root)[0].load_clean_stems()
    fault = faults.Fault(**spec_.fault)
    if fault.stem:
        stems[fault.stem] = faults.apply(fault, stems[fault.stem], sr)
    engine = OfflineEngine(stems, sr)
    engine.set_state(MixState.from_dict(mix_state))
    processed = engine.render_stems()
    return {g: graders._sum(processed, g) for g in graders.render_groups(spec_, songs_root)}


@pytest.mark.parametrize("fault, ans, state", [
    (GAIN, answer("fixed", "vox_lead", "gain"), {"vox_lead": {"gain_db": -6.0}}),
    (GAIN, answer("fixed", "vox_lead", "gain"), {"vox_lead": {"gain_db": -6.0}, "bass": {"gain_db": 2.0}}),
    (faults.Fault("polarity", "drums_overheads_1", 0), answer("fixed", "drums_overheads_2", "polarity"),
     {"drums_overheads_2": {"polarity": True}}),
    (faults.Fault("clipping", "vox_lead", 1, {"depth_db": 12.0}), answer("unfixable", "vox_lead", "clipping"), {}),
    (faults.Fault("control", None, 0), answer("no_fault"), {}),
    (faults.Fault("control", None, 0), answer("no_fault"), {"bass": {"pan": 0.4}}),
])
def test_grading_from_group_renders_matches_grading_a_mix_state(songs_root, fault, ans, state):
    """The FL baseline is graded from renders of groups of tracks. Given exact renders, that
    must give the same grade as the mix state would (apart from what renders can't tell)."""
    s = spec(fault)
    from_state = graders.grade(s, ans, state, songs_root)
    from_renders = graders.grade_renders(s, ans, _group_renders(s, state, songs_root), songs_root)
    for key in ("touched_other_stems", "invalid_mix_state"):
        from_state.pop(key)
        from_renders.pop(key)
    assert _same_grade(from_renders, from_state)


def _same_grade(a, b) -> bool:
    """Equal, with numbers within rounding. Residuals below -100 dB count as silence: summing
    two group renders leaves float noise (-240 dB) where one render would be exactly -inf."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same_grade(a[k], b[k]) for k in a)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if a <= -100 and b <= -100:
            return True
        return a == b or abs(a - b) <= 0.051
    return a == b


def test_render_groups_cover_every_stem_once(songs_root):
    pol = spec(faults.Fault("polarity", "drums_overheads_1", 0))
    groups = graders.render_groups(pol, songs_root)
    assert len(groups) == 3                                                     # accepted mics, others, other drums
    assert set().union(*groups[:2]) == {"drums_kick", "drums_overheads_1", "drums_overheads_2", "bass", "vox_lead"}
    assert not groups[0] & groups[1]
    assert graders.render_groups(spec(faults.Fault("control", None, 0)), songs_root) == [
        frozenset({"drums_kick", "drums_overheads_1", "drums_overheads_2", "bass", "vox_lead"})]


def test_no_note_mud_and_resonance_are_out_of_scope():
    """D83: taste faults with no client note don't count toward the headline pass rate."""
    assert not graders.in_scope({"fault_type": "mud", "hint_level": "none"})
    assert not graders.in_scope({"fault_type": "resonance", "hint_level": "none"})
    assert graders.in_scope({"fault_type": "mud", "hint_level": "vague"})
    assert graders.in_scope({"fault_type": "gain", "hint_level": "none"})
    assert graders.in_scope({"fault_type": "control", "hint_level": "none"})


def test_grades_carry_their_scope(songs_root):
    r = graders.grade(spec(GAIN), answer("fixed", "vox_lead", "gain"), {"vox_lead": {"gain_db": -6.0}}, songs_root)
    assert r["in_scope"] is True
