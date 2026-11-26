"""Task generation (seeded, reproducible) and task materialization (DESIGN.md §4.2, D18).

A *task spec* says: this song, this fault on this stem at this severity, this hint.
Specs are small JSON and are committed in tasks/<set>.json. They contain the answers,
so the agent under test must never be able to read them (DESIGN.md §4.8).

A *workspace* is what the agent gets for one run: every stem as a WAV (one of them
faulty) plus a brief. Workspaces are built just before a run and thrown away after,
because a full copy of a song's stems is hundreds of MB.

Usage:
    python -m zosimix.tasks generate --set smoke --n 6 --seed 7
    python -m zosimix.tasks generate --set full --n 30 --seed 42
    python -m zosimix.tasks generate --set dev --n 21 --seed 72 --songs-root data/dev_songs \n        --types gain resonance mud pan clipping control
    python -m zosimix.tasks materialize full-001 --dest <folder outside the repo>
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from zosimix import audio, faults, targets
from zosimix.songs import DATA_ROOT, Song, family_of, find_song, list_songs

TASKS_DIR = Path(__file__).resolve().parents[2] / "tasks"
MAX_DUPLICATE_DRAWS = 20     # duplicates in a row before a fault type gives up its turn (D49)

BASE_INSTRUCTION = (
    "These are the stems of a song's mix. Find and fix any problems with the mix. "
    "Some problems cannot be fixed with mixing tools: report those instead of trying to fix them. "
    "If nothing is wrong, say so and leave the mix alone."
)


def vague_hint(fault: faults.Fault) -> str:
    """A client's note: points in the right direction without naming the stem or the cause."""
    family = family_of(fault.stem) if fault.stem else ""
    match fault.type:
        case "gain":
            return (f"The {family} feel too loud." if fault.params["gain_db"] > 0
                    else f"I can barely hear the {family}.")
        case "polarity":
            return "The drums sound thin and lack punch."
        case "resonance":
            return f"Something in the {family} sounds harsh or ringy."
        case "mud":
            return "The mix feels muddy and boxy."
        case "pan":
            return "The stereo image feels lopsided."
        case "clipping":
            return "Something sounds distorted."
        case "control":
            return "Can you check this mix over before we send it out?"
    raise ValueError(fault.type)


@dataclass
class TaskSpec:
    task_id: str
    song_id: str
    fault: dict
    hint_level: str          # "vague" or "none"
    hint: str                # empty when hint_level == "none"

    @property
    def brief(self) -> str:
        return BASE_INSTRUCTION + (f"\n\nClient note: \"{self.hint}\"" if self.hint else "")


def generate(set_name: str, n: int, seed: int, songs: list[Song],
             fault_types: list[str] | None = None) -> list[TaskSpec]:
    """Stratified sampling (D47):
      - cycle through the fault types so each appears about equally,
      - among the songs that can host that fault, prefer the least-used one,
      - cycle severity (subtle, clear, severe) per fault type; pick stem and hint at random,
      - never emit the same (song, fault, stem, severity, hint) twice. Polarity has only a
        few possible stems in the whole dataset, so without this it repeats itself,
      - if a type draws MAX_DUPLICATE_DRAWS duplicates in a row, it gives its turn to the next type."""
    types = list(fault_types or faults.FAULT_TYPES)   # a subset when some type has no host (D72)
    rng = random.Random(seed)
    loaded = {s.song_id: s.load_clean_stems()[:2] for s in songs}
    eligible = {(sid, ft): ft == "control" or bool(faults.eligible_stems(ft, *loaded[sid]))
                for sid in loaded for ft in types}
    order = types[:]
    rng.shuffle(order)
    specs: list[TaskSpec] = []
    seen: set[tuple] = set()
    uses = dict.fromkeys(loaded, 0)
    per_type = {ft: rng.randrange(len(faults.SEVERITIES[ft])) for ft in types}  # random start
    turn = 0          # position in the fault-type rotation; moves on after each new task
    misses = 0        # duplicates drawn in a row for the current turn's type
    attempts = 0
    while len(specs) < n:
        attempts += 1
        if attempts > 50 * n:
            raise ValueError(f"could not find {n} distinct tasks; the dataset is too small")
        fault_type = order[turn % len(order)]
        hosts = [sid for sid in loaded if eligible[(sid, fault_type)]]
        if not hosts:
            raise ValueError(f"no song can host a {fault_type} fault")
        fewest = min(uses[sid] for sid in hosts)
        song_id = rng.choice([sid for sid in hosts if uses[sid] == fewest])
        stems, sr = loaded[song_id]
        severity = per_type[fault_type] % len(faults.SEVERITIES[fault_type])     # cycle sizes evenly
        try:
            fault = faults.choose(fault_type, severity, stems, sr, rng)
        except ValueError:          # this song can't carry this size of a mix-sized fault (D69)
            fault = None
        hint_level = rng.choice(["vague", "none"])
        if fault is None:
            misses += 1
            if misses == MAX_DUPLICATE_DRAWS:
                turn += 1
                misses = 0
            continue
        key =(song_id, fault.type, fault.stem, fault.severity, hint_level)
        if key in seen:
            misses += 1
            if misses == MAX_DUPLICATE_DRAWS:   # this type looks used up: give its turn to the next type
                turn += 1
                misses = 0
            continue
        misses = 0
        turn += 1
        seen.add(key)
        uses[song_id] += 1
        per_type[fault_type] += 1
        i = len(specs)
        specs.append(TaskSpec(
            task_id=f"{set_name}-{i + 1:03d}",
            song_id=song_id,
            fault=fault.to_dict(),
            hint_level=hint_level,
            hint=vague_hint(fault) if hint_level == "vague" else "",
        ))
    return specs


REVISED_TYPES = ("mud", "resonance")


def revise_eq_faults(source: list[TaskSpec], set_name: str, seed: int, songs: list[Song]) -> list[TaskSpec]:
    """A new version of a set where only the mud and resonance faults are redrawn with the
    mix-sized rule (D69). Each redrawn task keeps its song, severity and hint level; every
    other task is copied unchanged, so its earlier results still describe the same task.
    Task numbers are kept: `full-002` becomes `full-v2-002`."""
    rng = random.Random(seed)
    loaded: dict[str, tuple] = {}
    out = []
    for spec in source:
        number = spec.task_id.rsplit("-", 1)[1]
        if spec.fault["type"] not in REVISED_TYPES:
            out.append(TaskSpec(**{**asdict(spec), "task_id": f"{set_name}-{number}"}))
            continue
        if spec.song_id not in loaded:
            song = next(s for s in songs if s.song_id == spec.song_id)
            loaded[spec.song_id] = song.load_clean_stems()[:2]
        stems, sr = loaded[spec.song_id]
        fault = faults.choose(spec.fault["type"], spec.fault["severity"], stems, sr, rng)
        out.append(TaskSpec(f"{set_name}-{number}", spec.song_id, fault.to_dict(), spec.hint_level,
                            vague_hint(fault) if spec.hint_level == "vague" else ""))
    return out


def save(set_name: str, seed: int, specs: list[TaskSpec], derived_from: str | None = None) -> Path:
    TASKS_DIR.mkdir(exist_ok=True)
    path = TASKS_DIR / f"{set_name}.json"
    data = {"set": set_name, "seed": seed, **({"derived_from": derived_from} if derived_from else {}),
            "tasks": [asdict(s) for s in specs]}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load(set_name: str) -> list[TaskSpec]:
    data = json.loads((TASKS_DIR / f"{set_name}.json").read_text(encoding="utf-8"))
    return [TaskSpec(**t) for t in data["tasks"]]


def faulty_stems(spec: TaskSpec, songs_root: Path = DATA_ROOT) -> tuple[dict[str, np.ndarray], int]:
    """The song's clean stems with the task's fault baked into one of them: what the agent gets."""
    song = find_song(spec.song_id, songs_root)
    stems, sr, _ = song.load_clean_stems()
    fault = faults.Fault(**spec.fault)
    if fault.stem:
        stems = {**stems, fault.stem: faults.apply(fault, stems[fault.stem], sr)}
    return stems, sr


def write_brief(spec: TaskSpec, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "brief.md").write_text(spec.brief + "\n", encoding="utf-8")


def materialize(spec: TaskSpec, dest: Path, songs_root: Path = DATA_ROOT, target: dict | None = None) -> Path:
    """Build the agent's workspace for one task.

    Every stem is written the same way (stereo, 32-bit float) so file format, channel
    count or name can't give away which stem was changed. `target` is the leave-one-out
    tonal target (targets.target_for): built from other songs only, so safe for the agent.
    """
    stems, sr = faulty_stems(spec, songs_root)
    stems_dir = dest / "stems"
    for name, a in stems.items():
        audio.write(stems_dir / f"{name}.wav", audio.to_stereo(np.asarray(a)), sr)
    write_brief(spec, dest)
    if target is not None:
        (dest / "tonal_target.json").write_text(json.dumps(target, indent=1), encoding="utf-8")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--set", required=True)
    g.add_argument("--n", type=int, required=True)
    g.add_argument("--seed", type=int, required=True)
    g.add_argument("--songs-root", type=Path, default=DATA_ROOT,
                   help="where the songs are; the dev set uses data/dev_songs (D72)")
    g.add_argument("--types", nargs="+", choices=faults.FAULT_TYPES, help="only these fault types")
    r = sub.add_parser("revise", help="redraw only the mud/resonance faults of an existing set (D69)")
    r.add_argument("--from", dest="source", required=True)
    r.add_argument("--set", required=True)
    r.add_argument("--seed", type=int, required=True)
    m = sub.add_parser("materialize")
    m.add_argument("task_id")
    m.add_argument("--dest", type=Path, required=True)
    args = ap.parse_args()

    if args.cmd in ("generate", "revise"):
        if args.cmd == "generate":
            specs = generate(args.set, args.n, args.seed, list_songs(args.songs_root), args.types)
            path = save(args.set, args.seed, specs)
        else:
            specs = revise_eq_faults(load(args.source), args.set, args.seed, list_songs())
            path = save(args.set, args.seed, specs, derived_from=args.source)
        for s in specs:
            f = s.fault
            print(f"{s.task_id}  {s.song_id:<34} {f['type']:<9} {f['stem']!s:<26} sev {f['severity']}  "
                  f"{s.hint_level:<5} {s.hint}")
        print(f"wrote {path}")
    else:
        set_name = args.task_id.rsplit("-", 1)[0]
        spec = next(s for s in load(set_name) if s.task_id == args.task_id)
        print(f"workspace: {materialize(spec, args.dest, target=targets.target_for(spec.song_id))}")


if __name__ == "__main__":
    main()
