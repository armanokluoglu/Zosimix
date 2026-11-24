"""Tests for songs, fault injection and task generation, using a small synthetic song.

The synthetic song is built so each fault type has exactly the stems it needs:
two drum mics (polarity), a centred vocal (pan), a wide stereo guitar (not pannable),
and enough mid-range content for resonance and mud.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from zosimix import audio, faults, tasks
from zosimix.songs import Song, check_stem_sum, list_songs

SR = 44100
SECONDS = 3


def _tone(freqs: list[float], rng: np.random.Generator) -> np.ndarray:
    t = np.arange(SR * SECONDS) / SR
    sig = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) for f in freqs)
    return 0.1 * sig / len(freqs)


@pytest.fixture
def songs_root(tmp_path):
    rng = np.random.default_rng(0)
    root = tmp_path / "songs"
    folder = root / "synthetic-01"
    kick = _tone([60, 120], rng)[:, None]
    stems = {
        "drums_kick": kick,
        "drums_overheads": 0.7 * kick + 0.02 * rng.standard_normal((SR * SECONDS, 1)),
        "bass": _tone([55, 110, 220, 330], rng)[:, None],
        "vox_lead": _tone([220, 440, 880, 1760, 3520], rng)[:, None],
        "guitar_wide": 0.05 * rng.standard_normal((SR * SECONDS, 2)),
    }
    for name, a in stems.items():
        audio.write(folder / "stems" / f"{name}.wav", a, SR)
    audio.write(folder / "reference.wav", audio.mix(stems), SR)
    (folder / "song.json").write_text(json.dumps({"song_id": "synthetic-01"}), encoding="utf-8")
    return root


def _song(root) -> Song:
    return list_songs(root)[0]


def test_stem_sum_check_is_exact_when_reference_is_the_sum(songs_root):
    check = check_stem_sum(_song(songs_root))
    assert check.exact and check.plausible
    assert abs(check.gain_db) < 0.01


def test_eligibility_matches_what_each_fault_needs(songs_root):
    stems, sr = _song(songs_root).load_stems()
    assert faults.eligible_stems("polarity", stems, sr) == ["drums_kick"]       # overheads are the reference
    assert "guitar_wide" not in faults.eligible_stems("pan", stems, sr)         # already wide, can't be "un-centred"
    assert "vox_lead" in faults.eligible_stems("pan", stems, sr)
    assert faults.eligible_stems("control", stems, sr) == []


def test_gain_fault_changes_level_by_exactly_the_requested_db(songs_root):
    stems, sr = _song(songs_root).load_stems()
    fault = faults.Fault("gain", "vox_lead", 1, {"gain_db": -6.0})
    out = faults.apply(fault, stems["vox_lead"], sr)
    assert audio.gain_to_db(audio.rms(out) / audio.rms(stems["vox_lead"])) == pytest.approx(-6.0, abs=1e-6)


def test_polarity_fault_inverts(songs_root):
    stems, sr = _song(songs_root).load_stems()
    out = faults.apply(faults.Fault("polarity", "drums_kick", 0), stems["drums_kick"], sr)
    np.testing.assert_allclose(out, -stems["drums_kick"])


def test_resonance_boosts_energy_at_its_frequency(songs_root):
    stems, sr = _song(songs_root).load_stems()
    fault = faults.Fault("resonance", "vox_lead", 2, {"freq_hz": 880.0, "gain_db": 12.0, "q": 8.0})
    out = faults.apply(fault, stems["vox_lead"], sr)
    f, before = audio.long_term_spectrum(stems["vox_lead"], sr)
    _, after = audio.long_term_spectrum(out, sr)
    at_880 = np.argmin(np.abs(f - 880))
    at_3520 = np.argmin(np.abs(f - 3520))
    assert after[at_880] - before[at_880] == pytest.approx(12.0, abs=1.0)    # boosted
    assert abs(after[at_3520] - before[at_3520]) < 1.0                        # far away: untouched


def test_pan_law_keeps_centre_at_unity_and_moves_energy_to_one_side():
    assert faults.pan_gains(0.0) == pytest.approx((1.0, 1.0))
    left, right = faults.pan_gains(0.9)
    assert right > 1.0 > left


def test_clipping_caps_peaks(songs_root):
    stems, sr = _song(songs_root).load_stems()
    a = stems["vox_lead"]
    out = faults.apply(faults.Fault("clipping", "vox_lead", 1, {"depth_db": 12.0}), a, sr)
    assert audio.peak(out) == pytest.approx(audio.peak(a) * audio.db_to_gain(-12.0))


def test_generate_is_reproducible_and_covers_fault_types(songs_root):
    songs = list_songs(songs_root)
    first = tasks.generate("t", 14, seed=42, songs=songs)
    second = tasks.generate("t", 14, seed=42, songs=songs)
    assert [t.fault for t in first] == [t.fault for t in second]
    assert {t.fault["type"] for t in first} == set(faults.FAULT_TYPES)


def test_hints_never_name_the_stem(songs_root):
    for spec in tasks.generate("t", 14, seed=1, songs=list_songs(songs_root)):
        stem = spec.fault["stem"]
        if stem:
            assert stem not in spec.brief


def test_workspace_hides_which_stem_changed(songs_root, tmp_path):
    spec = tasks.TaskSpec("t-001", "synthetic-01",
                          faults.Fault("pan", "vox_lead", 2, {"pan": 0.9}).to_dict(), "none", "")
    ws = tasks.materialize(spec, tmp_path / "ws", songs_root=songs_root)
    import soundfile as sf
    infos = [sf.info(str(p)) for p in sorted((ws / "stems").glob("*.wav"))]
    assert len(infos) == 5
    assert {(i.channels, i.subtype) for i in infos} == {(2, "FLOAT")}       # all identical format
    assert (ws / "brief.md").read_text(encoding="utf-8").startswith(tasks.BASE_INSTRUCTION)
    assert not any(p.name.endswith(".json") for p in ws.rglob("*"))         # no ground truth in workspace
