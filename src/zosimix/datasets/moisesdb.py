"""Pick a handful of MoisesDB songs and copy them into Zosimix's song layout.

MoisesDB (Pereira et al. 2023, arXiv:2307.15913; CC BY-NC-SA 4.0) is about 80 GB. We only
need about 5 songs, so this module surveys the whole dataset by reading only its small
data.json files, ranks songs by how well they suit the benchmark, and imports the chosen ones.

On-disk layout of MoisesDB (from the official loader):
    <root>/<provider>/<track_id>/data.json
    <root>/<provider>/<track_id>/<stemName>/<file_id>.<ext>
data.json lists stems; each stem has tracks with a trackType ("kick drum", "overheads", ...).
The dataset defines the mixture as the plain sum of all tracks, so there is no separate mix file.

Usage:
    python -m zosimix.datasets.moisesdb survey <root>
    python -m zosimix.datasets.moisesdb import <root> <track_id> [<track_id> ...]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from zosimix import audio
from zosimix.songs import DATA_ROOT

ATTRIBUTION = ("MoisesDB by Pereira, Araújo, Korzeniowski and Vogl (2023), arXiv:2307.15913, "
               "licensed CC BY-NC-SA 4.0")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class Candidate:
    track_id: str
    folder: Path
    artist: str
    song: str
    genre: str
    # our stem name -> list of source files that get summed into it
    stems: dict[str, list[Path]] = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def drum_mics(self) -> list[str]:
        return [s for s in self.stems if s.startswith("drums_")]

    @property
    def has_overheads(self) -> bool:
        return any("overhead" in s for s in self.drum_mics)

    @property
    def has_lead_vocal(self) -> bool:
        return any(s.startswith("vocals_") and "lead" in s for s in self.stems)

    def score(self) -> float:
        """Higher is better. What the benchmark needs (DESIGN.md §4.1-4.2):
        separate drum mics incl. overheads (polarity faults), a lead vocal (pan, gain),
        8-14 stems (rich enough for an agent, small enough to build an FL template by hand),
        and a length of 2.5-5 minutes."""
        s = 0.0
        s += 3 if len(self.drum_mics) >= 3 and self.has_overheads else 0
        s += 2 if self.has_lead_vocal else 0
        s += 2 if 8 <= len(self.stems) <= 14 else 0
        s += 1 if 150 <= self.seconds <= 300 else 0
        return s


def _our_stem_name(stem_name: str, track_type: str) -> str:
    return f"{_slug(stem_name)}_{_slug(track_type)}".replace("-", "_")


def read_candidate(data_json: Path) -> Candidate:
    data = json.loads(data_json.read_text(encoding="utf-8"))
    folder = data_json.parent
    c = Candidate(folder.name, folder, data.get("artist", ""), data.get("song", ""), data.get("genre", ""))
    for stem in data.get("stems", []):
        for track in stem.get("tracks", []):
            name = _our_stem_name(stem["stemName"], track["trackType"])
            path = folder / stem["stemName"] / f"{track['id']}.{track['extension']}"
            c.stems.setdefault(name, []).append(path)
    first = next((p for paths in c.stems.values() for p in paths if p.exists()), None)
    if first:
        c.seconds = sf.info(str(first)).duration
    return c


def survey(root: Path) -> list[Candidate]:
    return sorted((read_candidate(p) for p in root.glob("*/*/data.json")),
                  key=lambda c: (-c.score(), c.genre, c.song))


def import_song(c: Candidate) -> Path:
    """Sum each stem's source files and write it in the common layout (32-bit float)."""
    song_id = f"moisesdb-{_slug(c.artist)[:20]}-{_slug(c.song)[:30]}".strip("-")
    folder = DATA_ROOT / song_id
    rate = None
    for name, paths in c.stems.items():
        parts = [audio.read(p) for p in paths]
        rates = {sr for _, sr in parts}
        if len(rates) != 1 or (rate and rates != {rate}):
            raise ValueError(f"{c.track_id}: mixed sample rates {rates}; resampling isn't supported yet")
        rate = rates.pop()
        length = min(a.shape[0] for a, _ in parts)
        summed = np.sum([audio.to_stereo(a[:length]) if any(x.shape[1] == 2 for x, _ in parts) else a[:length]
                         for a, _ in parts], axis=0)
        audio.write(folder / "stems" / f"{name}.wav", summed, rate)
    (folder / "song.json").write_text(json.dumps({
        "song_id": song_id,
        "title": c.song,
        "artist": c.artist,
        "genre": c.genre,
        "dataset": "MoisesDB",
        "moisesdb_track_id": c.track_id,
        "license": "CC BY-NC-SA 4.0",
        "attribution": ATTRIBUTION,
        "reference": "none: MoisesDB defines the mixture as the plain stem sum",
    }, indent=2), encoding="utf-8")
    return folder


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("survey")
    s.add_argument("root", type=Path)
    s.add_argument("--top", type=int, default=25)
    i = sub.add_parser("import")
    i.add_argument("root", type=Path)
    i.add_argument("track_ids", nargs="+")
    args = ap.parse_args()

    candidates = survey(args.root)
    if args.cmd == "survey":
        print(f"{len(candidates)} songs found\n")
        for c in candidates[: args.top]:
            print(f"score {c.score():.0f}  {c.track_id}  {c.genre:<14} {c.artist[:18]:<18} {c.song[:28]:<28} "
                  f"{len(c.stems):2d} stems  {len(c.drum_mics)} drum mics  {c.seconds / 60:4.1f} min")
    else:
        by_id = {c.track_id: c for c in candidates}
        for track_id in args.track_ids:
            print(f"imported {import_song(by_id[track_id])}")


if __name__ == "__main__":
    main()
