"""The listening check (D75): clips are loudness-matched and short, answers map back to versions,
and the report reads the counts the right way round."""

from __future__ import annotations

import numpy as np
import pyloudnorm
import pytest

from zosimix import listening

SR = 44100


def test_clips_are_loudness_matched_and_faded():
    rng = np.random.default_rng(0)
    loud = 0.3 * rng.standard_normal((SR * 20, 2))
    quiet = 0.03 * rng.standard_normal((SR * 20, 2))
    window = slice(SR * 2, SR * 2 + int(listening.CLIP_S * SR))
    a, b = listening._clip(loud, window, SR), listening._clip(quiet, window, SR)
    meter = pyloudnorm.Meter(SR)
    assert meter.integrated_loudness(a) == pytest.approx(listening.CLIP_LUFS, abs=0.1)
    assert meter.integrated_loudness(b) == pytest.approx(listening.CLIP_LUFS, abs=0.1)
    assert len(a) == int(listening.CLIP_S * SR) and abs(a[0]).max() == 0.0


def test_the_window_follows_the_loud_part_of_the_faulty_stem():
    stem = np.zeros((SR * 60, 1))
    stem[SR * 30: SR * 45] = 0.5                       # only plays from 30 s to 45 s
    w = listening._window(stem, SR)
    assert SR * 28 <= w.start <= SR * 33


KEY = {"trials": [
    {"trial": 1, "kind": "same", "a": "broken", "b": "broken"},
    {"trial": 2, "kind": "clean_vs_broken", "a": "broken", "b": "clean"},
    {"trial": 3, "kind": "fixed_vs_broken", "a": "repaired", "b": "broken"},
    {"trial": 4, "kind": "fixed_vs_broken", "a": "broken", "b": "repaired"},
    {"trial": 5, "kind": "clean_vs_fixed", "a": "clean", "b": "repaired"},
]}


def test_answers_map_back_to_versions_whatever_side_they_were_on():
    answers = {"answers": [{"trial": 1, "answer": "none"}, {"trial": 2, "answer": "b"},
                           {"trial": 3, "answer": "a"}, {"trial": 4, "answer": "b"},
                           {"trial": 5, "answer": "none"}]}
    s = listening.analyze(KEY, answers)
    assert s["same"] == {"n": 1, "no difference": 1}
    assert s["clean_vs_broken"] == {"n": 1, "clean": 1}
    assert s["fixed_vs_broken"] == {"n": 2, "repaired": 2}
    text = listening.report(s, "AB")
    assert "repaired preferred 2/2" in text and "clean preferred 1/1" in text


def test_unanswered_trials_are_left_out():
    s = listening.analyze(KEY, {"answers": [{"trial": 3, "answer": None}]})
    assert s == {}


def test_report_cites_albumdb_exactly_as_citations_md():
    cite = listening.albumdb_citation()
    text = (listening.REPO / "CITATIONS.md").read_text(encoding="utf-8")
    body = cite.split("\n\n", 2)[2].strip()
    assert body in text and "mckenzie_2026_19683001" in body and "MoisesDB" not in body
