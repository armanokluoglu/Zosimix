"""Parity check: the same mix state through the offline engine and through FL (DESIGN.md §3.3, D64).

The agent's previews and the graders use the offline engine (D36). That is only fair if
FL, the real DAW, would have produced the same mix. So for one task per song we build the
faulty song exactly as the agent receives it, and render three mix states on both engines:

  neutral  the mix as handed over
  repair   the ideal fix for that task's fault
  busy     a deliberately heavy state that uses every control on several stems
  lowpass  a low-pass on one stem

and compare: the residual (FL minus offline, relative to the mix), the largest difference
in any of the 8 analysis bands, and the loudness difference. The low-pass is judged on
the spectrum only: its magnitude matches FL's, its phase does not (D64).

Usage:
    python -m zosimix.fl.parity                 # writes results/parity.md and results/parity.json
    python -m zosimix.fl.parity --tasks full-001 full-007
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from zosimix import analysis, audio, faults, tasks
from zosimix.engines.fl import FLEngine
from zosimix.engines.offline import OfflineEngine
from zosimix.mixstate import MixState
from zosimix.songs import list_songs

RESULTS = Path(__file__).resolve().parents[3] / "results"

# Pass thresholds (D64). The residual is relative to the whole mix; band and loudness
# differences are what the graders and the agent's measurements actually look at.
MAX_RESIDUAL_DB = -40.0
MAX_BAND_DIFF_DB = 0.1
MAX_LUFS_DIFF = 0.05


def repair_state(fault: faults.Fault) -> MixState:
    """The textbook fix for a fault (the same fixes the engine tests prove exact)."""
    p, s = fault.params, fault.stem
    if fault.type == "gain":
        return MixState.from_dict({s: {"gain_db": -p["gain_db"]}})
    if fault.type == "polarity":
        return MixState.from_dict({s: {"polarity": True}})
    if fault.type in ("resonance", "mud"):
        return MixState.from_dict({s: {"eq": [{"type": "peaking", "freq_hz": p["freq_hz"],
                                               "gain_db": -p["gain_db"], "q": p["q"]}]}})
    if fault.type == "pan":
        return MixState.from_dict({s: {"pan": -p["pan"], "gain_db": -audio.gain_to_db(math.cos(p["pan"] * math.pi / 2))}})
    return MixState()                                   # clipping and control: leave the mix alone


def lowpass_state(stem_names: list[str]) -> MixState:
    """A low-pass on one stem, on its own: the one control whose *phase* differs from FL's (D64)."""
    return MixState.from_dict({stem_names[3]: {"eq": [{"type": "lowpass", "freq_hz": 9000, "q": 1.2}]}})


def busy_state(stem_names: list[str]) -> MixState:
    """Every control on the first six stems: boosts past the fader's range, deep cuts,
    pan, width both ways, polarity and every EQ type except low-pass (see lowpass_state)."""
    recipes = [
        {"gain_db": 8.0, "eq": [{"type": "peaking", "freq_hz": 2500, "gain_db": -6, "q": 8},
                                {"type": "high_shelf", "freq_hz": 8000, "gain_db": 3, "q": 0.7}]},
        {"gain_db": -20.0, "pan": -0.4, "width": 1.6},
        {"pan": 0.7, "polarity": True, "width": 0.3},
        {"eq": [{"type": "highpass", "freq_hz": 120}, {"type": "low_shelf", "freq_hz": 200, "gain_db": -4, "q": 0.9}]},
        {"gain_db": 3.0, "eq": [{"type": "peaking", "freq_hz": 300, "gain_db": 5, "q": 1},
                                {"type": "peaking", "freq_hz": 900, "gain_db": -3, "q": 3},
                                {"type": "peaking", "freq_hz": 4000, "gain_db": 2, "q": 0.5}]},
        {"pan": -1.0, "width": 0.0, "gain_db": -6.0},
    ]
    return MixState.from_dict(dict(zip(stem_names, recipes, strict=False)))


def compare(offline: np.ndarray, fl: np.ndarray, sr: int, waveform: bool = True) -> dict:
    """waveform=False skips the residual test: for the low-pass, only the spectrum must match."""
    residual = audio.gain_to_db(audio.rms(fl - offline) / audio.rms(offline))
    bands = [analysis.band_levels(*analysis.spectrum(x, sr)) for x in (offline, fl)]
    band_diff = max(abs(bands[1][b] - bands[0][b]) for b in bands[0])
    lufs = [analysis.loudness_lufs(x, sr) for x in (offline, fl)]
    result = {"residual_db": round(residual, 1), "band_diff_db": round(band_diff, 3),
              "lufs_diff": round(lufs[1] - lufs[0], 3), "waveform_tested": waveform}
    result["pass"] = bool((residual <= MAX_RESIDUAL_DB or not waveform) and band_diff <= MAX_BAND_DIFF_DB
                          and abs(result["lufs_diff"]) <= MAX_LUFS_DIFF)
    return result


def check_task(spec: tasks.TaskSpec) -> list[dict]:
    song = next(s for s in list_songs() if s.song_id == spec.song_id)
    clean, sr, _ = song.load_clean_stems()
    fault = faults.Fault(**spec.fault)
    stems = {n: faults.apply(fault, a, sr) if n == fault.stem else a for n, a in clean.items()}
    rows = []
    names = sorted(stems)
    for label, state in (("neutral", MixState()), ("repair", repair_state(fault)),
                         ("busy", busy_state(names)), ("lowpass", lowpass_state(names))):
        out = {}
        for name, cls in (("offline", OfflineEngine), ("fl", FLEngine)):
            engine = cls(stems, sr)
            engine.set_state(state)
            started = time.monotonic()
            out[name] = engine.render()
            out[f"{name}_s"] = round(time.monotonic() - started, 1)
        row = {"task_id": spec.task_id, "song_id": spec.song_id, "fault": fault.type, "state": label,
               "fl_seconds": out["fl_s"], **compare(out["offline"], out["fl"], sr, waveform=label != "lowpass")}
        print(f"  {spec.task_id} {label:<8} residual {row['residual_db']:6.1f} dB  bands {row['band_diff_db']:.3f} dB  "
              f"LUFS {row['lufs_diff']:+.3f}  FL {row['fl_seconds']:.0f} s  {'ok' if row['pass'] else 'FAIL'}", flush=True)
        rows.append(row)
    return rows


def one_task_per_song(set_name: str) -> list[tasks.TaskSpec]:
    seen, picked = set(), []
    for spec in tasks.load(set_name):
        if spec.song_id not in seen:
            seen.add(spec.song_id)
            picked.append(spec)
    return picked


def report(rows: list[dict]) -> str:
    passed = sum(r["pass"] for r in rows)
    summary = (f"{passed}/{len(rows)} renders within tolerance (residual <= {MAX_RESIDUAL_DB:.0f} dB, "
               f"every band within {MAX_BAND_DIFF_DB} dB, loudness within {MAX_LUFS_DIFF} LU). "
               "Generated by `python -m zosimix.fl.parity` (D64).")
    lines = ["# Parity check: offline engine vs FL Studio 20.9.2", "", summary, "",
             "| task | song | fault | state | residual (dB) | worst band (dB) | LUFS diff | FL render (s) | ok |",
             "|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['task_id']} | {r['song_id']} | {r['fault']} | {r['state']} | {r['residual_db']} | "
              f"{r['band_diff_db']} | {r['lufs_diff']:+} | {r['fl_seconds']:.0f} | "
              f"{('yes' if r['pass'] else 'NO') + ('' if r['waveform_tested'] else ' (spectrum only)')} |"
              for r in rows]
    note = ("The low-pass rows are judged on bands and loudness only: PEQ2's low-pass has the same "
            "magnitude as Zosimix's but a different phase (about one sample of extra delay at high "
            "frequencies), so its waveform residual is not expected to be small (D64).")
    lines += ["", note, "", data_citations()]
    return "\n".join(lines) + "\n"


def data_citations() -> str:
    """The dataset citations, copied from CITATIONS.md so they stay exactly as written there
    (CLAUDE.md: every results page that uses MoisesDB or AlbumDB data must cite them)."""
    text = (RESULTS.parent / "CITATIONS.md").read_text(encoding="utf-8")
    return "## Data\n\nThe songs come from MoisesDB and AlbumDB.\n\n" + text[text.index("## MoisesDB"):].strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", default="full")
    ap.add_argument("--tasks", nargs="*", help="task ids (default: the first task of each song)")
    args = ap.parse_args()
    specs = tasks.load(args.set)
    chosen = [s for s in specs if s.task_id in args.tasks] if args.tasks else one_task_per_song(args.set)
    rows = []
    for spec in chosen:
        rows += check_task(spec)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "parity.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    (RESULTS / "parity.md").write_text(report(rows), encoding="utf-8")
    print(f"{sum(r['pass'] for r in rows)}/{len(rows)} within tolerance; wrote {RESULTS / 'parity.md'}")


if __name__ == "__main__":
    main()
