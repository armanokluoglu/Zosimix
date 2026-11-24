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
from zosimix.songs import DATA_ROOT, Song, family_of, list_songs

TASKS_DIR = Path(__file__).resolve().parents[2] / "tasks"

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


def generate(set_name: str, n: int, seed: int, songs: list[Song]) -> list[TaskSpec]:
    """Stratified sampling: cycle through the fault types so each appears about equally,
    and pick the song, severity, stem and hint level at random for each task."""
    rng = random.Random(seed)
    loaded = {s.song_id: s.load_clean_stems()[:2] for s in songs}
    order = faults.FAULT_TYPES[:]
    rng.shuffle(order)
    specs: list[TaskSpec] = []
    for i in range(n):
        fault_type = order[i % len(order)]
        song_ids = list(loaded)
        rng.shuffle(song_ids)
        for song_id in song_ids:                   # first song that can host this fault
            stems, sr = loaded[song_id]
            if fault_type == "control" or faults.eligible_stems(fault_type, stems, sr):
                break
        else:
            raise ValueError(f"no song can host a {fault_type} fault")
        severity = rng.randrange(len(faults.SEVERITIES[fault_type]))
        fault = faults.choose(fault_type, severity, stems, sr, rng)
        hint_level = rng.choice(["vague", "none"])
        specs.append(TaskSpec(
            task_id=f"{set_name}-{i + 1:03d}",
            song_id=song_id,
            fault=fault.to_dict(),
            hint_level=hint_level,
            hint=vague_hint(fault) if hint_level == "vague" else "",
        ))
    return specs


def save(set_name: str, seed: int, specs: list[TaskSpec]) -> Path:
    TASKS_DIR.mkdir(exist_ok=True)
    path = TASKS_DIR / f"{set_name}.json"
    path.write_text(json.dumps({"set": set_name, "seed": seed, "tasks": [asdict(s) for s in specs]}, indent=2),
                    encoding="utf-8")
    return path


def load(set_name: str) -> list[TaskSpec]:
    data = json.loads((TASKS_DIR / f"{set_name}.json").read_text(encoding="utf-8"))
    return [TaskSpec(**t) for t in data["tasks"]]


def materialize(spec: TaskSpec, dest: Path, songs_root: Path = DATA_ROOT, target: dict | None = None) -> Path:
    """Build the agent's workspace for one task.

    Every stem is written the same way (stereo, 32-bit float) so file format, channel
    count or name can't give away which stem was changed. `target` is the leave-one-out
    tonal target (targets.target_for): built from other songs only, so safe for the agent.
    """
    song = next(s for s in list_songs(songs_root) if s.song_id == spec.song_id)
    stems, sr, _ = song.load_clean_stems()
    fault = faults.Fault(**spec.fault)
    stems_dir = dest / "stems"
    for name, clean in stems.items():
        out = faults.apply(fault, clean, sr) if name == fault.stem else clean
        audio.write(stems_dir / f"{name}.wav", audio.to_stereo(np.asarray(out)), sr)
    (dest / "brief.md").write_text(spec.brief + "\n", encoding="utf-8")
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
    m = sub.add_parser("materialize")
    m.add_argument("task_id")
    m.add_argument("--dest", type=Path, required=True)
    args = ap.parse_args()

    if args.cmd == "generate":
        specs = generate(args.set, args.n, args.seed, list_songs())
        path = save(args.set, args.seed, specs)
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
