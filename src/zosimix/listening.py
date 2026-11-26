"""Blind A/B listening check: do the graders agree with ears? (DESIGN.md §4.9, D75)

A sanity check, not a study. One listener (the builder, maybe a friend) hears pairs of short
clips in random order and says which sounds better mixed, or that they can't tell. The pairs:

  same               the same clip twice                    control: "no difference" expected
  clean_vs_broken    the clean mix vs a badly broken one    control: clean expected
  fixed_vs_broken    a repair the grader PASSED vs broken   repaired expected
  failed_vs_broken   a repair the grader FAILED vs broken   less often preferred than the above
  clean_vs_fixed     clean vs a repair the grader PASSED    hard to tell apart, if the grader is right

Only AlbumDB songs are used (CC BY 4.0; DESIGN.md §3: AlbumDB supplies all audio used publicly).
Every clip is 12 s from where the faulty stem is loudest, the same window for all versions of a
task, and every clip is matched to the same loudness so "louder" can't win a comparison.

The page and its clips go in <session>/page/; the answer key (which clip is which) goes in
<session>/key.json, outside the page folder, so the listener can't peek at it.

Usage:
    python -m zosimix.listening build --out C:/zosimix/listening/session-1
    (listen: open <out>/page/index.html, answer, click "Download answers")
    python -m zosimix.listening analyze --out C:/zosimix/listening/session-1 --answers <answers.json>
"""

from __future__ import annotations

import argparse
import collections
import functools
import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyloudnorm

from zosimix import audio, faults, tasks
from zosimix.engines.offline import OfflineEngine
from zosimix.mixstate import MixState
from zosimix.songs import find_song

REPO = Path(__file__).resolve().parents[2]
RUNS = Path("C:/zosimix/runs")
SOURCE_RUNS = ["full-1", "full-2", "full-3-targeted", "dev-v3", "dev-v5", "dev-after3", "dev-after4"]
SETS = ["full", "full-v2", "dev"]
CLIP_S = 12.0
CLIP_LUFS = -23.0
FADE_S = 0.02
PREROLL_S = 1.0                  # rendered before each clip so filters have settled
PER_KIND = 6                     # main pairs per kind
CONTROLS = 3                     # control pairs per kind
FAULTS_HEARD = ("gain", "pan", "mud", "resonance")    # clipping and control tasks have no repair to hear


@dataclass
class Candidate:
    run: str
    spec: tasks.TaskSpec
    row: dict
    mix_state: dict

    @property
    def passed(self) -> bool:
        return bool(self.row["grade"]["pass"])


def _rows(run: str) -> list[dict]:
    """A run's graded rows; the regraded ones when they exist (D73)."""
    path = RUNS / run / "regraded.jsonl"
    if not path.exists():
        path = RUNS / run / "results.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def candidates() -> list[Candidate]:
    """Runs on AlbumDB songs that changed the mix, on faults you can hear, with a saved mix state."""
    specs = {s.task_id: s for name in SETS for s in tasks.load(name)}
    # The original full set's mud and resonance faults barely changed the mix and were redrawn
    # in full-v2 (D69); they would make inaudible "broken" clips, so they are left out.
    superseded = {s.task_id for s in tasks.load("full") if s.fault["type"] in ("mud", "resonance")}
    out = []
    for run in SOURCE_RUNS:
        if not (RUNS / run).exists():
            continue
        for row in _rows(run):
            spec = specs.get(row["task_id"])
            if (row.get("status") != "done" or spec is None or row["task_id"] in superseded
                    or not spec.song_id.startswith("albumdb")
                    or spec.fault["type"] not in FAULTS_HEARD or row["config"] == "flmcp"):
                continue
            answer_path = RUNS / run / "answers" / f"{row['task_id']}-{row['config']}-{row['repeat']}.json"
            if not answer_path.exists():
                continue
            mix_state = json.loads(answer_path.read_text(encoding="utf-8")).get("mix_state") or {}
            changed = any(v != {"gain_db": 0.0, "pan": 0.0, "polarity": False, "width": 1.0, "eq": []}
                          for v in mix_state.values() if isinstance(v, dict))
            if changed:
                out.append(Candidate(run, spec, row, mix_state))
    return out


def _pick(pool: list[Candidate], n: int, rng: random.Random) -> list[Candidate]:
    """Up to n candidates, one per task, spread over fault types as evenly as the pool allows."""
    by_task: dict[str, Candidate] = {}
    for c in rng.sample(pool, len(pool)):
        by_task.setdefault(c.spec.task_id, c)
    by_fault = collections.defaultdict(list)
    for c in by_task.values():
        by_fault[c.spec.fault["type"]].append(c)
    picked: list[Candidate] = []
    while len(picked) < n and any(by_fault.values()):
        for fault_type in sorted(by_fault):
            if by_fault[fault_type] and len(picked) < n:
                picked.append(by_fault[fault_type].pop())
    return picked


def _window(stem: np.ndarray, sr: int) -> slice:
    """The CLIP_S seconds where the faulty stem is loudest, so the fault is audible."""
    length = int(CLIP_S * sr)
    if len(stem) <= length:
        return slice(0, len(stem))
    # Energy of every window starting on a whole second, from a running sum (a convolution
    # with a one-second kernel took minutes on a four-minute song).
    total = np.concatenate([[0.0], np.cumsum((audio.to_stereo(stem) ** 2).mean(axis=1))])
    starts = np.arange(0, len(stem) - length, sr)
    best = int(starts[np.argmax(total[starts + length] - total[starts])])
    return slice(best, best + length)


def _clip(x: np.ndarray, window: slice, sr: int) -> np.ndarray:
    """Cut, match loudness to CLIP_LUFS, fade the edges, and keep it from clipping."""
    y = audio.to_stereo(x)[window].copy()
    loudness = pyloudnorm.Meter(sr).integrated_loudness(y)
    if np.isfinite(loudness):
        y *= audio.db_to_gain(CLIP_LUFS - loudness)
    fade = int(FADE_S * sr)
    ramp = np.linspace(0.0, 1.0, fade)[:, None]
    y[:fade] *= ramp
    y[-fade:] *= ramp[::-1]
    peak = audio.peak(y)
    return y / peak * 0.98 if peak > 0.98 else y


@functools.lru_cache(maxsize=1)
def _song(song_id: str) -> tuple[dict[str, np.ndarray], int]:
    clean, sr, _ = find_song(song_id).load_clean_stems()
    return clean, sr


def _versions(c: Candidate) -> tuple[dict[str, np.ndarray], int]:
    """Clean, broken and this run's repaired mix, all cut from the same window.

    Only the window is rendered, plus PREROLL_S before it so the EQ filters have settled."""
    clean, sr = _song(c.spec.song_id)
    fault = faults.Fault(**c.spec.fault)
    broken = dict(clean)
    broken[fault.stem] = faults.apply(fault, clean[fault.stem], sr)
    window = _window(broken[fault.stem], sr)
    start = max(0, window.start - int(PREROLL_S * sr))
    cut = slice(start, window.stop)
    inside = slice(window.start - start, window.stop - start)

    def part(stems: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return {n: a[cut] for n, a in stems.items()}

    engine = OfflineEngine(part(broken), sr)
    engine.set_state(MixState.from_dict(c.mix_state))
    return {"clean": _clip(audio.mix(part(clean)), inside, sr), "broken": _clip(audio.mix(part(broken)), inside, sr),
            "repaired": _clip(engine.render(), inside, sr)}, sr


def build(out: Path, seed: int = 75) -> Path:
    """Write the page, its clips and the answer key. Returns the page's path."""
    rng = random.Random(seed)
    pool = candidates()
    passed = [c for c in pool if c.passed]
    failed = [c for c in pool if not c.passed and c.row["grade"].get("verdict") == "fixed"]
    fixed_vs_broken = _pick(passed, PER_KIND, rng)
    clean_vs_fixed = _pick([c for c in passed if c not in fixed_vs_broken], PER_KIND, rng)
    failed_vs_broken = _pick(failed, PER_KIND, rng)
    severe = [c for c in pool if c.spec.fault["severity"] == 2]
    controls = _pick(severe, CONTROLS, rng)
    same = _pick(pool, CONTROLS, rng)

    page_dir = out / "page"
    (page_dir / "clips").mkdir(parents=True, exist_ok=True)
    clip_no = 0
    trials, key = [], []

    def write(x: np.ndarray, sr: int) -> str:
        nonlocal clip_no
        clip_no += 1
        name = f"clips/c{clip_no:03d}.wav"            # opaque: says nothing about what it is
        audio.write(page_dir / name, x, sr)
        return name

    plan = ([("same", c, "broken", "broken") for c in same]
            + [("clean_vs_broken", c, "clean", "broken") for c in controls]
            + [("fixed_vs_broken", c, "repaired", "broken") for c in fixed_vs_broken]
            + [("failed_vs_broken", c, "repaired", "broken") for c in failed_vs_broken]
            + [("clean_vs_fixed", c, "clean", "repaired") for c in clean_vs_fixed])
    rng.shuffle(plan)
    order = sorted(range(len(plan)), key=lambda i: plan[i][1].spec.song_id)    # one song in memory at a time
    rendered = {}
    for i in order:
        rendered[i] = _versions(plan[i][1])
    for i, (kind, c, first, second) in enumerate(plan, start=1):
        versions, sr = rendered[i - 1]
        if rng.random() < 0.5:
            first, second = second, first
        a, b = write(versions[first], sr), write(versions[second], sr)
        trials.append({"trial": i, "a": a, "b": b})
        key.append({"trial": i, "kind": kind, "a": first, "b": second, "task_id": c.spec.task_id,
                    "fault": c.spec.fault["type"], "severity": c.spec.fault["severity"], "run": c.run,
                    "config": c.row["config"], "repeat": c.row["repeat"], "grader_pass": c.passed})
        print(f"  trial {i:2d}: {kind}")
    (out / "key.json").write_text(json.dumps({"seed": seed, "trials": key}, indent=1), encoding="utf-8")
    template = Path(__file__).with_name("listening_page.html")
    html = template.read_text(encoding="utf-8").replace("/*TRIALS*/[]", json.dumps(trials))
    page = page_dir / "index.html"
    page.write_text(html, encoding="utf-8")
    return page


# ---------------------------------------------------------------- analysis

def _preferred(answer: str, trial: dict) -> str | None:
    """Which version the listener preferred ("clean", "broken", "repaired"), or None for no difference."""
    return {"a": trial["a"], "b": trial["b"]}.get(answer)


def analyze(key: dict, answers: dict) -> dict:
    """Per kind: how often each version was preferred, and how often the listener couldn't tell."""
    by_trial = {a["trial"]: a["answer"] for a in answers["answers"]}
    out: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for t in key["trials"]:
        answer = by_trial.get(t["trial"])
        if answer is None:
            continue
        choice = _preferred(answer, t)
        out[t["kind"]]["n"] += 1
        out[t["kind"]][choice or "no difference"] += 1
    return {kind: dict(c) for kind, c in out.items()}


def report(summary: dict, listener: str) -> str:
    def share(kind: str, what: str) -> str:
        c = summary.get(kind, {})
        return f"{c.get(what, 0)}/{c.get('n', 0)}" if c.get("n") else "-"

    lines = [
        f"# Blind listening check ({listener})",
        "",
        "One listener, blind A/B, 12 s loudness-matched clips from AlbumDB songs (DESIGN.md §4.9, D75).",
        "A sanity check of whether the graders agree with ears, not a study.",
        "",
        "| Pair | What was heard | Expected if the graders are right |",
        "|---|---|---|",
        f"| Same clip twice (control) | 'no difference' {share('same', 'no difference')} | all 'no difference' |",
        f"| Clean vs badly broken (control) | clean preferred {share('clean_vs_broken', 'clean')} | clean every time |",
        (f"| Passed repair vs broken | repaired preferred {share('fixed_vs_broken', 'repaired')},"
        f" no difference {share('fixed_vs_broken', 'no difference')} | repaired mostly |"),
        (f"| Failed repair vs broken | repaired preferred {share('failed_vs_broken', 'repaired')},"
        f" no difference {share('failed_vs_broken', 'no difference')} | repaired less often than above |"),
        (f"| Clean vs passed repair | 'no difference' {share('clean_vs_fixed', 'no difference')},"
        f" clean {share('clean_vs_fixed', 'clean')}, repaired {share('clean_vs_fixed', 'repaired')} |"
        " hard to tell apart |"),
        "",
    ]
    return "\n".join(lines)


def albumdb_citation() -> str:
    """The AlbumDB section of CITATIONS.md, verbatim: only AlbumDB audio is used here."""
    text = (REPO / "CITATIONS.md").read_text(encoding="utf-8")
    start = text.index("## AlbumDB")
    nxt = text.find("\n## ", start + 1)
    return "## Data\n\nThe clips come from AlbumDB.\n\n" + (text[start:] if nxt == -1 else text[start:nxt]).strip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--seed", type=int, default=75)
    a = sub.add_parser("analyze")
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--answers", type=Path, required=True)
    a.add_argument("--report", type=Path, default=REPO / "results" / "listening.md")
    args = ap.parse_args()
    if args.cmd == "build":
        print(f"page: {build(args.out, args.seed)}")
    else:
        key = json.loads((args.out / "key.json").read_text(encoding="utf-8"))
        answers = json.loads(args.answers.read_text(encoding="utf-8"))
        text = report(analyze(key, answers), answers.get("listener", "listener")) + "\n" + albumdb_citation()
        args.report.write_text(text, encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
