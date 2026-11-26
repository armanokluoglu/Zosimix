"""The oracle check (D72): could a perfect reader of the harness's measurements single out the
faulty stem at all?

For each task, every stem of the faulty song (what the agent gets) is scored on the one
measurement that fits the task's fault, and the faulty stem's rank is reported. Rank 1 means
the measurement points straight at it; a low rank means even a flawless agent using that
measurement would most likely blame another stem. No agent runs, no API use.

Measurements (`MEASURES`, one per fault type, the same numbers the tools show):
  clipping   flat-topped peak runs per minute (overview's clips/min)
  polarity   how much flipping the stem would restore the drum bus's low end (phase tool)
  pan        |left/right balance| among near-mono stems (overview's bal and corr)
  mud        low-mid band share against the stem's family, in spreads (tonal_balance)
  resonance  height of the stem's strongest persistent spectral bump (spectrum tool)
  gain       |loudness relative to the mix| against the family's typical value in the other
             songs. The harness has no tool for this (it was tried and removed, D54); the
             number says what such a tool could do at best.

Usage:
    python -m zosimix.oracle --set full-v2
"""

from __future__ import annotations

import argparse
import collections
import math

import numpy as np

from zosimix import analysis, audio, faults, graders, targets, tasks
from zosimix.songs import family_of, list_songs

NEAR_MONO_CORR = 0.9          # pan faults are only made on centred stems, so compare like with like


def _mud(stems, sr, target):
    out = {}
    for name, a in stems.items():
        ref = target["families"].get(family_of(name))
        if ref:
            mean, spread = ref["lowmid"]
            out[name] = (targets.shape(audio.to_stereo(a), sr)["lowmid"] - mean) / spread
    return out


def _resonance(stems, sr, _target):
    out = {}
    for name, a in stems.items():
        peaks = analysis.persistent_peaks(audio.to_stereo(a), sr, 300, 8000, limit=1)
        out[name] = peaks[0].excess_db if peaks else 0.0
    return out


def _pan(stems, sr, _target):
    out = {}
    for name, a in stems.items():
        x = audio.to_stereo(a)
        if analysis.lr_correlation(x) > NEAR_MONO_CORR:
            out[name] = abs(analysis.balance_db(x))
    return out


def _clipping(stems, sr, _target):
    return {name: analysis.flat_top_runs_per_min(audio.to_stereo(a), sr) for name, a in stems.items()}


def _polarity(stems, sr, _target):
    drums = {n: audio.to_stereo(a) for n, a in stems.items() if family_of(n) == "drums"}
    return {n: r["flip_db"] for n, r in analysis.phase_report(drums, sr).items()}


_LEVELS: dict[str, dict[str, float]] = {}


def _song_levels(song_id: str) -> dict[str, float]:
    """Each clean stem's loudness relative to its song's mix, in LU (cached per song)."""
    if song_id not in _LEVELS:
        song = next(s for s in list_songs() if s.song_id == song_id)
        stems, sr, _ = song.load_clean_stems()
        mix = analysis.loudness_lufs(audio.mix(stems), sr)
        _LEVELS[song_id] = {n: analysis.loudness_lufs(audio.to_stereo(a), sr) - mix for n, a in stems.items()}
    return _LEVELS[song_id]


def _gain(stems, sr, _target, song_id):
    typical = collections.defaultdict(list)
    for song in list_songs():
        if song.song_id != song_id:
            for n, level in _song_levels(song.song_id).items():
                if math.isfinite(level):
                    typical[family_of(n)].append(level)
    mix = analysis.loudness_lufs(audio.mix(stems), sr)
    out = {}
    for name, a in stems.items():
        values = typical.get(family_of(name), [])
        level = analysis.loudness_lufs(audio.to_stereo(a), sr) - mix
        if len(values) >= 3 and math.isfinite(level):
            out[name] = abs(level - np.mean(values)) / max(np.std(values), 1.5)
    return out


MEASURES = {"mud": _mud, "resonance": _resonance, "pan": _pan, "clipping": _clipping,
            "polarity": _polarity, "gain": _gain}


def rank(spec: tasks.TaskSpec) -> dict | None:
    """Where the measurement ranks the faulty stem among all stems it applies to (1 = top)."""
    fault_type = spec.fault["type"]
    if fault_type not in MEASURES:
        return None
    stems, sr = tasks.faulty_stems(spec)
    target = targets.target_for(spec.song_id)
    measure = MEASURES[fault_type]
    scores = measure(stems, sr, target, spec.song_id) if fault_type == "gain" else measure(stems, sr, target)
    ordered = sorted(scores, key=lambda n: -scores[n])
    accept = graders.acceptable_stems(faults.Fault(**spec.fault), stems, sr) & set(scores)
    best = min((ordered.index(n) + 1 for n in accept), default=None)
    return {"task_id": spec.task_id, "fault": fault_type, "severity": spec.fault["severity"],
            "rank": best, "of": len(ordered), "top": ordered[0] if ordered else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True)
    args = ap.parse_args()
    rows = [r for r in (rank(s) for s in tasks.load(args.set)) if r]
    for r in rows:
        print(f"{r['task_id']}  {r['fault']:<9} sev {r['severity']}  rank {r['rank']} of {r['of']}  (top: {r['top']})")
    print()
    by = collections.defaultdict(list)
    for r in rows:
        by[r["fault"]].append(r["rank"])
    for fault_type, ranks in sorted(by.items()):
        first = sum(1 for x in ranks if x == 1)
        top3 = sum(1 for x in ranks if x is not None and x <= 3)
        print(f"{fault_type:<9} singled out {first}/{len(ranks)}, in the top 3 {top3}/{len(ranks)}")


if __name__ == "__main__":
    main()
